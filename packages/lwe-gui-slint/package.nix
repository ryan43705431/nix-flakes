{
  lib,
  stdenv,
  python3,
  fetchurl,
  autoPatchelfHook,
  makeWrapper,
  # slint.abi3.so 的链接依赖（autoPatchelfHook 靠 buildInputs 解 RPATH）
  libxkbcommon,
  systemd,
  libinput,
  mesa,
  fontconfig,
  freetype,
  # 只在运行时 dlopen、不进 DT_NEEDED 的库：winit 的 wayland 后端与 Skia 的 GL surface
  wayland,
  libGL,
  # 运行时经 PATH 调用的外部命令
  ffmpeg,
  linux-wallpaperengine,
  procps,
}:

let
  version = (lib.importTOML ./pyproject.toml).project.version;

  # Slint 只有预发布 wheel；sdist 需要完整 Rust 工具链，因此按 wheel 打包。
  # manylinux_2_35 要求 glibc >= 2.35（NixOS 26.05 满足），cp311-abi3 在 3.13 上按 abi3 兼容。
  slint = python3.pkgs.buildPythonPackage rec {
    pname = "slint";
    version = "1.18.1b1";

    format = "wheel";
    src = fetchurl {
      url = "https://files.pythonhosted.org/packages/05/cd/a0694640c60a9ffc3572b8366686162fee146f26638247b9cb402cc28c9f/slint-1.18.1b1-cp311-abi3-manylinux_2_35_x86_64.whl";
      hash = "sha256-JytdEK4WgtxFWt59HJvO3ZES2vCJd5SmVzdZMQM1yz0=";
    };

    nativeBuildInputs = [ autoPatchelfHook ];
    buildInputs = [
      stdenv.cc.cc.lib
      libxkbcommon
      systemd
      libinput
      mesa
      fontconfig
      freetype
    ];

    dontStrip = true;
    doCheck = false;
    pythonImportsCheck = [ "slint" ];

    meta = {
      description = "Python bindings for the Slint GUI toolkit";
      homepage = "https://slint.dev";
      license = lib.licenses.gpl3Only;
      platforms = [ "x86_64-linux" ];
    };
  };
in
python3.pkgs.buildPythonApplication {
  pname = "lwe-gui-slint";
  inherit version;

  pyproject = true;
  # 只把构建需要的东西放进 store：.venv（uv 托管的解释器）与 __pycache__ 不进
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./pyproject.toml
      ./src
      ./ui
      ./lwe-gui-slint.desktop
    ];
  };

  build-system = [ python3.pkgs.hatchling ];
  dependencies = [ slint ];
  nativeBuildInputs = [ makeWrapper ];

  # ui/ 不在 wheel 里（不在 src/lwe_gui_slint 下），单独放 share，再用 LWE_UI_DIR 指过去
  postInstall = ''
    mkdir -p $out/share/lwe-gui-slint
    cp -r ui $out/share/lwe-gui-slint/ui
    install -Dm644 lwe-gui-slint.desktop $out/share/applications/lwe-gui-slint.desktop
  '';

  makeWrapperArgs = [
    "--prefix PATH : ${lib.makeBinPath [ linux-wallpaperengine ffmpeg procps ]}"
    "--set LWE_UI_DIR ${placeholder "out"}/share/lwe-gui-slint/ui"
    # libwayland-client / libEGL / mesa 驱动是 dlopen 进来的，不在 slint.abi3.so 的
    # DT_NEEDED 里，autoPatchelfHook 的 RPATH 也就不含它们。缺了这行 winit 建不出
    # wayland 事件循环，slint 退回 linuxkms 后端并报
    # 「presenting framebuffer on screen: Permission denied (os error 13)」。
    "--prefix LD_LIBRARY_PATH : ${lib.makeLibraryPath [ wayland libGL mesa ]}"
  ];

  doCheck = false;
  pythonImportsCheck = [ "lwe_gui_slint.main" ];

  meta = {
    description = "Linux Wallpaper Engine 壁纸管理器（Python + Slint）";
    mainProgram = "lwe-gui-slint";
    license = lib.licenses.gpl3Only;
    platforms = [ "x86_64-linux" ];
  };
}
