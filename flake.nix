{
  description = "lojix-test — hermetic behavioral replay for public Lojix schema refusal";

  inputs = {
    nixpkgs.url = "github:LiGoldragon/nixpkgs?ref=main";

    blueprint.url = "github:numtide/blueprint";
    blueprint.inputs.nixpkgs.follows = "nixpkgs";

    crane.url = "github:ipetkov/crane";

    fenix.url = "github:nix-community/fenix";
    fenix.inputs.nixpkgs.follows = "nixpkgs";

    lojix-red.url = "github:LiGoldragon/lojix/a36de1c68d68ab4834e318c0a55c371389a84b67";
    lojix-red.inputs.nixpkgs.follows = "nixpkgs";

    lojix-green.url = "github:LiGoldragon/lojix/94d8b69a546560e9d3c8300c6114e8dac7df67ea";
    lojix-green.inputs.nixpkgs.follows = "nixpkgs";

    lojix-migrate.url = "github:LiGoldragon/lojix/97946f";
    lojix-migrate.inputs.nixpkgs.follows = "nixpkgs";

    lojix-migrate-green.url = "github:LiGoldragon/lojix/b93b51";
    lojix-migrate-green.inputs.nixpkgs.follows = "nixpkgs";

    lojix-migrate-final.url = "github:LiGoldragon/lojix/6be34e";
    lojix-migrate-final.inputs.nixpkgs.follows = "nixpkgs";

    # Kept independently pinned: this is the public producer that wrote the
    # v5 fixture, and also the binary used by the terminal-only rollback probe.
    lojix-old-runtime.url = "github:LiGoldragon/lojix/3fc95f0cf4eaf14ff62898c4783ebbc670fdf96b";
    lojix-old-runtime.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = inputs: inputs.blueprint { inherit inputs; };
}
