//! 有上界的封面图片缓存。
//!
//! 为什么需要它：gpui 的 sprite atlas **不会自动回收图片** —— 只有显式调用
//! `App::drop_image` 才会把纹理从显存里放掉。应用不提供 `ImageCache` 时，
//! 每张见过的封面都会永远留在显存（实测每张约 1.7MB），切歌/滚动多了就是几百 MB。
//!
//! 这里按「解码后字节数」做上限，超了就按 LRU 淘汰，并在淘汰时把图交给
//! `cx.drop_image` 释放 —— 也就是 gpui 文档说的用法。

use std::collections::{HashMap, VecDeque};
use std::sync::{Arc, Mutex};

use gpui::{
    hash, App, AppContext, Asset as _, AssetLogger, Entity, ImageAssetLoader, ImageCache,
    ImageCacheError, RenderImage, Resource, Window,
};

/// 缓存预算（按解码后 RGBA 估：宽 × 高 × 4）。够留住几屏封面，又不会无界增长。
const BUDGET_BYTES: usize = 64 * 1024 * 1024;
/// 数量下限：预算再紧也至少留这么多张，免得把正在显示的那几张反复踢掉。
const MIN_KEEP: usize = 16;

/// 一张封面的槽位：解码完成后写进来（`None` 表示还在加载）。
type Slot = Arc<Mutex<Option<Result<Arc<RenderImage>, ImageCacheError>>>>;

struct Entry {
    slot: Slot,
    /// 解码后占的字节数，用于预算统计（加载完成前按 0 计）。
    bytes: usize,
}

pub struct CoverImageCache {
    entries: HashMap<u64, Entry>,
    /// LRU 顺序：队尾是最近用过的。
    order: VecDeque<u64>,
    bytes: usize,
}

impl CoverImageCache {
    pub fn new(cx: &mut App) -> Entity<Self> {
        let entity = cx.new(|_cx| Self {
            entries: HashMap::new(),
            order: VecDeque::new(),
            bytes: 0,
        });
        // 实体销毁时把还留着的图全部释放，避免退出前又漏一批。
        cx.observe_release(&entity, |cache, cx| {
            for (_, entry) in cache.entries.drain() {
                if let Some(Ok(image)) = entry.slot.lock().ok().and_then(|slot| slot.clone()) {
                    cx.drop_image(image, None);
                }
            }
        })
        .detach();
        entity
    }

    fn touch(&mut self, key: u64) {
        self.order.retain(|existing| *existing != key);
        self.order.push_back(key);
    }

    /// 超出预算就按 LRU 淘汰，并把图从图集里放掉。
    ///
    /// 只淘汰**已经解码完成**的条目：还在后台解码的条目如果这时被移出缓存，
    /// 解码出来的那张图就没有人再调 `drop_image`，会留成一张永不释放的纹理。
    /// 加载中的条目刚被 touch 过、本来就在队尾，跳过它不影响淘汰效果。
    fn evict(&mut self, window: &mut Window, cx: &mut App) {
        let mut rounds = 0;
        while self.bytes > BUDGET_BYTES && self.order.len() > MIN_KEEP && rounds < self.order.len()
        {
            rounds += 1;
            let Some(key) = self.order.pop_front() else {
                break;
            };
            let Some(entry) = self.entries.get(&key) else {
                continue;
            };
            let loaded = entry.slot.lock().ok().and_then(|slot| slot.clone());
            let bytes = entry.bytes;
            match loaded {
                // 解码完成的：记回字节数、把图交给 gpui 释放、移除条目。
                Some(Ok(image)) => {
                    self.bytes = self.bytes.saturating_sub(bytes);
                    self.entries.remove(&key);
                    cx.drop_image(image, Some(window));
                }
                // 加载失败的：没有纹理要放，直接移除条目。
                Some(Err(_)) => {
                    self.bytes = self.bytes.saturating_sub(bytes);
                    self.entries.remove(&key);
                }
                // 还在加载：挪到队尾，等它解码完再参与淘汰。
                None => self.order.push_back(key),
            }
        }
    }
}

impl ImageCache for CoverImageCache {
    fn load(
        &mut self,
        resource: &Resource,
        window: &mut Window,
        cx: &mut App,
    ) -> Option<Result<Arc<RenderImage>, ImageCacheError>> {
        let key = hash(resource);

        if let Some(entry) = self.entries.get(&key) {
            let slot = entry.slot.clone();
            let bytes_before = entry.bytes;
            self.touch(key);
            let image = slot.lock().ok().and_then(|slot| slot.clone());
            if let Some(Ok(loaded)) = &image {
                // 解码完成的那一张：把它的真实字节数记进预算，超了再淘汰。
                let bytes = loaded.as_bytes(0).map(|data| data.len()).unwrap_or(0);
                if bytes > 0 {
                    self.bytes = self.bytes.saturating_sub(bytes_before) + bytes;
                    if let Some(entry) = self.entries.get_mut(&key) {
                        entry.bytes = bytes;
                    }
                }
                self.evict(window, cx);
            }
            return image;
        }

        // 未命中：后台解码，完成后写进槽位并让请求方重绘一次。
        let slot: Slot = Arc::new(Mutex::new(None));
        self.entries.insert(
            key,
            Entry {
                slot: slot.clone(),
                bytes: 0,
            },
        );
        self.touch(key);

        let view = window.current_view();
        let executor = cx.background_executor().clone();
        let asset = AssetLogger::<ImageAssetLoader>::load(resource.clone(), cx);
        let task = executor.spawn(asset);
        cx.spawn(async move |cx| {
            let result = task.await;
            if let Ok(mut guard) = slot.lock() {
                *guard = Some(result);
            }
            // 让请求方重绘：它会在同一帧回来问缓存，这次就能拿到图。
            cx.update(|cx| cx.notify(view));
        })
        .detach();

        None
    }
}
