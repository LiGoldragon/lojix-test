{
  flake,
  pkgs,
  system,
  ...
}:
import ../modules/immutable-converter-replay.nix { inherit flake pkgs system; }
