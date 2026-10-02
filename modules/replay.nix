{
  flake,
  pkgs,
  system,
}:
let
  testName = "horizon_layout_change_refuses_v5_open_and_destructive_reset";
  command = "cargo test --offline --test schema_one_migration ${testName}";
  toolchain = flake.inputs.fenix.packages.${system}.complete.withComponents [
    "cargo"
    "rustc"
  ];
  craneLib = (flake.inputs.crane.mkLib pkgs).overrideToolchain toolchain;

  runTrial =
    {
      name,
      source,
      expected,
    }:
    let
      vendor = craneLib.vendorCargoDeps {
        src = source;
      };
    in
    pkgs.stdenvNoCC.mkDerivation {
      pname = "lojix-schema-refusal-${name}";
      version = "1";
      src = source;
      nativeBuildInputs = [
        toolchain
        pkgs.stdenv.cc
        pkgs.coreutils
        pkgs.findutils
        pkgs.gnugrep
      ];
      dontUnpack = true;
      buildPhase = ''
        runHook preBuild
        capture="$NIX_BUILD_TOP/capture"
        mkdir -p work .cargo "$capture"
        cp -R --no-preserve=mode,ownership "$src"/. work/
        chmod -R u+w work
        cp -R --no-preserve=mode,ownership ${vendor}/. .cargo/
        cd work
        set +e
        timeout --foreground 20m ${command} > "$capture/stdout" 2> "$capture/stderr"
        status=$?
        set -e
        printf '%s\n' "$status" > "$capture/status"

        require_stdout() {
          grep -F "$1" "$capture/stdout" || {
            echo "missing required stdout signature: $1" >&2
            cat "$capture/stdout" >&2
            cat "$capture/stderr" >&2
            exit 1
          }
        }

        if [ "${expected}" = red ]; then
          test "$status" -ne 0 || {
            echo 'red trial unexpectedly passed' >&2
            exit 1
          }
          require_stdout "test ${testName} ... FAILED"
          require_stdout 'new Horizon layout must refuse schema 5'
          require_stdout 'test result: FAILED. 0 passed; 1 failed;'
        else
          test "$status" -eq 0 || {
            echo 'green trial failed' >&2
            cat "$capture/stdout" >&2
            cat "$capture/stderr" >&2
            exit 1
          }
          require_stdout "test ${testName} ... ok"
          require_stdout 'test result: ok. 1 passed; 0 failed;'
        fi
        runHook postBuild
      '';
      installPhase = ''
        mkdir -p "$out"
        cp "$NIX_BUILD_TOP/capture"/{stdout,stderr,status} "$out/"
        printf '%s\n' '${command}' > "$out/command"
        printf '%s\n' '${expected}' > "$out/expected"
        printf '%s\n' 'HEADER REFUSAL' > "$out/coverage"
      '';
    };
in
{
  red = runTrial {
    name = "red";
    source = flake.inputs.lojix-red;
    expected = "red";
  };
  green = runTrial {
    name = "green";
    source = flake.inputs.lojix-green;
    expected = "green";
  };
}
