{
  description = "ryan 的个人 Nix 包集合";

  # 单独使用时拉这个 nixpkgs；被消费方引用时可在那边设
  # inputs.nix-flakes.inputs.nixpkgs.follows = "nixpkgs"，避免重复拉取。
  inputs.nixpkgs.url = "git+https://gh-proxy.com/https://github.com/NixOS/nixpkgs.git?ref=nixos-26.05&shallow=1";

  outputs =
    { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f (import nixpkgs { inherit system; }));

      # 目录约定：packages/<名字>/package.nix，一个目录一个包。
      # 传 newScope 让包之间能互相 callPackage 引用；新增包只加目录，这里不用改。
      packagesFor = pkgs: pkgs.lib.packagesFromDirectoryRecursive {
        inherit (pkgs) callPackage newScope;
        directory = ./packages;
      };
    in
    {
      packages = forAllSystems packagesFor;

      overlays.default = final: _prev: packagesFor final;

      formatter = forAllSystems (pkgs: pkgs.nixfmt-rfc-style);
    };
}
