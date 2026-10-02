{
  flake,
  pkgs,
  system,
  oldSource,
  oldRevision,
  fixtureDriver,
  rawOracle,
}:
let
  toolchain = flake.inputs.fenix.packages.${system}.complete.withComponents [
    "cargo"
    "rustc"
  ];
  crane = (flake.inputs.crane.mkLib pkgs).overrideToolchain toolchain;
  vendor = crane.vendorCargoDeps {
    src = oldSource;
    cargoLock = "${oldSource}/Cargo.lock";
  };
in
pkgs.stdenvNoCC.mkDerivation {
  pname = "lojix-old-runtime-rollback";
  version = oldRevision;
  src = oldSource;
  nativeBuildInputs = [
    toolchain
    pkgs.stdenv.cc
    pkgs.python3
    pkgs.coreutils
  ];
  dontUnpack = true;
  # The executable retained for inspection must be the exact bytes launched by
  # the probe; generic ELF fixup/stripping would otherwise mutate it afterward.
  dontFixup = true;
  buildPhase = ''
    mkdir work .cargo fixture capture; cp -R "$src"/. work/; chmod -R u+w work; cp -R ${vendor}/. .cargo/
    cargo build --offline --manifest-path work/Cargo.toml --package lojix-nexus --bin lojix-nexus
    sha256sum "$PWD/work/target/debug/lojix-nexus" > "$NIX_BUILD_TOP/capture/binary.sha256"
    ${fixtureDriver} "$NIX_BUILD_TOP/fixture"
    mkdir -p "$NIX_BUILD_TOP/fixture/xdg-state/lojix" "$NIX_BUILD_TOP/fixture/xdg-runtime"
    cp "$NIX_BUILD_TOP/fixture/old-rollback/store.db" "$NIX_BUILD_TOP/fixture/xdg-state/lojix/lojix.sema"
    LOJIX_ORACLE_SCHEMA=old ${rawOracle} SNAPSHOT "$NIX_BUILD_TOP/fixture/xdg-state/lojix/lojix.sema" > "$NIX_BUILD_TOP/capture/store-before.json"
    cp "$NIX_BUILD_TOP/fixture/old-startup.rkyv" "$NIX_BUILD_TOP/capture/archive-before.rkyv"
    ${pkgs.python3}/bin/python ${../fixtures/old-runtime-rollback.py} --nexus "$PWD/work/target/debug/lojix-nexus" --root "$NIX_BUILD_TOP/fixture" --output "$NIX_BUILD_TOP/capture"
    LOJIX_ORACLE_SCHEMA=old ${rawOracle} SNAPSHOT "$NIX_BUILD_TOP/fixture/xdg-state/lojix/lojix.sema" > "$NIX_BUILD_TOP/capture/store-after.json"
    cp "$NIX_BUILD_TOP/fixture/old-startup.rkyv" "$NIX_BUILD_TOP/capture/archive-after.rkyv"
    sha256sum "$NIX_BUILD_TOP/fixture/old-startup.rkyv" "$NIX_BUILD_TOP/fixture/xdg-state/lojix/lojix.sema" > "$NIX_BUILD_TOP/capture/final.sha256"
    ${pkgs.python3}/bin/python ${../fixtures/old-runtime-oracle.py} \
      --before "$NIX_BUILD_TOP/capture/store-before.json" \
      --after "$NIX_BUILD_TOP/capture/store-after.json" \
      --startup "$NIX_BUILD_TOP/capture/startup-evidence.json" \
      --output "$NIX_BUILD_TOP/capture/oracle.json"
  '';
  installPhase = ''mkdir -p "$out/bin"; cp -R "$NIX_BUILD_TOP/capture"/. "$out/"; cp "$PWD/work/target/debug/lojix-nexus" "$out/bin/lojix-nexus"; printf '%s\n' '${oldRevision}' > "$out/old-revision"'';
}
