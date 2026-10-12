{
  lib,
  makeRustPlatform,
  rustPackages_1_97,
  pkg-config,
  patchelf,
  makeBinaryWrapper,
  alsa-lib,
  dbus,
  fontconfig,
  freetype,
  libxkbcommon,
  libxcb,
  libX11,
  libXext,
  libGL,
  libgbm,
  vulkan-loader,
  wayland,
  chromium,
  xdg-utils,
}:

# SodaM:汽水音乐第三方原生客户端(GPUI + Rust),AGPL-3.0-or-later。
# 源码以 clone 后裁剪的形式放在本目录(来源见 UPSTREAM),src 直接取当前目录,
# 所以改本地代码后重建即可生效,不需要动 hash;但 Cargo.lock 变了必须重算 cargoHash。
#   - 上游 gpui 依赖 pin Rust 1.97.1,nixpkgs 26.05 默认 rustc 是 1.95,故换 rustPackages_1_97;
#   - Cargo.lock 里 5 个 git 依赖(gpui/libresoda/font-kit/scap/xim-rs)在 vendor 固定输出
#     派生内用 git 的 url.insteadOf 重写到 gh.acmsz.top 镜像(本机直连 github git 不可达);
#   - vendor 产物里含 Cargo.lock,所以换上游版本后 cargoHash 必变;
#   - Vulkan/EGL/wayland/xkbcommon/gbm 是运行时 dlopen,必须显式补 rpath;
#   - 扫码登录要真实 Chromium(QISHUI_CHROMIUM_PATH)与 xdg-open。
let
  version = (lib.importTOML ./Cargo.toml).workspace.package.version;

  rustPlatform = makeRustPlatform {
    rustc = rustPackages_1_97.rustc;
    cargo = rustPackages_1_97.cargo;
  };
in
rustPlatform.buildRustPackage {
  pname = "sodam";
  inherit version;

  # 已去掉上游 .git;target/ 由仓库 .gitignore 挡在外面
  src = ./.;

  cargoHash = "sha256-vhI60OGGwx24wg0U654TupSpfj9pnrklySNT7YJaRNI=";

  depsExtraArgs.env = {
    GIT_CONFIG_COUNT = "1";
    GIT_CONFIG_KEY_0 = "url.https://gh.acmsz.top/https://github.com/.insteadOf";
    GIT_CONFIG_VALUE_0 = "https://github.com/";
  };

  # 上游 scripts/build.sh 同样限 4 并发/6G 内存;8 并发 rustc 会顶满本机 15G
  env.NIX_BUILD_CORES = "4";

  nativeBuildInputs = [
    pkg-config
    patchelf
    makeBinaryWrapper
  ];

  buildInputs = [
    alsa-lib # rodio/cpal 播放
    dbus
    fontconfig
    freetype
    libxkbcommon # 含 libxkbcommon-x11
    libxcb
    libX11
    libXext
    libGL # libglvnd,提供 libEGL/libGL
    libgbm
    vulkan-loader
    wayland
  ];

  # 上游测试依赖网络与真实账号数据
  doCheck = false;

  postInstall = ''
    install -Dm644 crates/sodam/assets/brand/sodam-logo.png \
      $out/share/icons/hicolor/256x256/apps/sodam.png
  '';

  postFixup = ''
    # 运行时 dlopen:libvulkan.so.1(ash/wgpu),libEGL.so.1(libglvnd),
    # libwayland-client.so.0,libxkbcommon.so.0,libgbm.so.1,libX11/libXext
    patchelf $out/bin/sodam --add-rpath ${
      lib.makeLibraryPath [
        libGL
        vulkan-loader
        wayland
        libxkbcommon
        libgbm
        libX11
        libXext
      ]
    }
    # 签名页/扫码登录要真实 Chromium;二次验证窗口用系统浏览器,需要 xdg-open
    wrapProgram $out/bin/sodam \
      --set QISHUI_CHROMIUM_PATH ${lib.getExe chromium} \
      --prefix PATH : ${lib.makeBinPath [ xdg-utils ]}
  '';

  meta = {
    description = "Native Qishui Music (汽水音乐) desktop client built with GPUI";
    homepage = "https://github.com/sodahub-org/sodam";
    license = lib.licenses.agpl3Plus;
    mainProgram = "sodam";
    platforms = [ "x86_64-linux" ];
    sourceProvenance = [ lib.sourceTypes.fromSource ];
  };
}
