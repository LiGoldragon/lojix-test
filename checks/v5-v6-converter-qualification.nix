{
  flake,
  pkgs,
  system,
  ...
}:
let
  red = import ../modules/v5-v6-qualification.nix {
    inherit flake pkgs system;
    source = flake.inputs.lojix-migrate;
    sourceRevision = "97946fd13059b3da56007af162708855d0494b25";
    expectedConverterStatus = 2;
    expectedError = "Table 'quarantined-row' does not exist";
  };
  wrongKeyRed = import ../modules/v5-v6-qualification.nix {
    inherit flake pkgs system;
    source = flake.inputs.lojix-migrate-green;
    sourceRevision = "b93b51ababf51395439d2c8d1cf37052f2a91a72";
    expectedConverterStatus = 2;
    expectedError = "unknown configuration key";
  };
  green = import ../modules/v5-v6-qualification.nix {
    inherit flake pkgs system;
    source = flake.inputs.lojix-migrate-final;
    sourceRevision = "6be34e8141f2bef26510004197d3256a762380a1";
    expectedConverterStatus = 0;
    expectedError = "";
    runMigrationCases = true;
  };
  oldRuntime = import ../modules/old-runtime-rollback.nix {
    inherit flake pkgs system;
    oldSource = flake.inputs.lojix-old-runtime;
    oldRevision = "3fc95f";
    fixtureDriver = "${green}/qualification-driver";
    rawOracle = "${green}/raw-snapshot-oracle";
  };
in
pkgs.runCommand "lojix-v5-v6-converter-qualification" { } ''
  mkdir -p "$out"
  ln -s ${red} "$out/red"
  ln -s ${wrongKeyRed} "$out/wrong-key-red"
  ln -s ${green} "$out/green"
  ln -s ${oldRuntime} "$out/old-runtime-rollback"
''
