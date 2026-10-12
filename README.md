# nix-flakes

ryan 的个人 Nix 包集合。仓库自身是 flake，输出 `packages.<system>.<名字>` 与 `overlays.default`。

## 包列表

| 包 | 说明 |
| --- | --- |
| `lwe-gui-slint` | Linux Wallpaper Engine 壁纸管理器（Python + Slint） |
| `sodam` | 汽水音乐第三方客户端（GPUI + Rust，源码 vendor 在本目录，AGPL-3.0-or-later） |

> `sodam` 的上游源码是 clone 后裁剪放在 `packages/sodam`（去掉 `.git`、`docs/`），
> 版本与来源记在同目录 `UPSTREAM`；更新用消费方仓库里的 `sodam-update`。
> 构建需要能访问 GitHub 镜像：`Cargo.lock` 里 5 个 git 依赖经 `gh.acmsz.top` 重写抓取。

## 使用

### 直接构建

```bash
nix build github:ryan43705431/nix-flakes#lwe-gui-slint
./result/bin/lwe-gui-slint
```

### 装进 NixOS 配置

```nix
# flake.nix
inputs.nix-flakes.url = "git+https://gh-proxy.com/https://github.com/ryan43705431/nix-flakes.git?shallow=1";
# 复用消费方的 nixpkgs，不重复拉取
inputs.nix-flakes.inputs.nixpkgs.follows = "nixpkgs";
```

```nix
# 任意模块里
user.home.packages = [
  inputs.nix-flakes.packages.${pkgs.stdenv.hostPlatform.system}.lwe-gui-slint
];
```

### overlay

```nix
nixpkgs.overlays = [ inputs.nix-flakes.overlays.default ];
# 之后可以直接写 pkgs.lwe-gui-slint
```

## 新增包

只需加 `packages/<名字>/package.nix`（一个 `callPackage` 可调用的函数），`flake.nix` 不用改。

`package.nix` 的参数由 nixpkgs 顶层解析，因此 `lib`、`stdenv`、`python3`、`fetchurl`、`makeWrapper`
这类都能直接声明；包之间也能互相引用（聚合层传了 `newScope`）。

目录里除 `package.nix` 以外的文件不会被当成包，可以放补丁、源码、桌面项等。

## 平台

`x86_64-linux`。`lwe-gui-slint` 依赖的 Slint 预发布 wheel 没有其他架构可用的构建。

## 许可

GPL-3.0。`lwe-gui-slint` 依赖的 Slint Python 绑定是 GPLv3 / 商业双许可，取 GPLv3 一侧。
