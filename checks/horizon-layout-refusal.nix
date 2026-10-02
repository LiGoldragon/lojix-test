{
  flake,
  pkgs,
  system,
  ...
}:
let
  replay = import ../modules/replay.nix {
    inherit flake pkgs system;
  };
  inherit (replay) green red;
in
pkgs.runCommand "lojix-horizon-layout-refusal-replay" { } ''
  mkdir -p "$out"
  ln -s ${red} "$out/red"
  ln -s ${green} "$out/green"
''
