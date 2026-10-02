{ pkgs, flake, ... }:
pkgs.runCommand "lint"
  {
    nativeBuildInputs = [
      pkgs.nixfmt
      pkgs.deadnix
      pkgs.statix
    ];
  }
  ''
    cd ${flake}
    find . -name '*.nix' -exec nixfmt --check {} +
    deadnix --fail .
    statix check .
    touch "$out"
  ''
