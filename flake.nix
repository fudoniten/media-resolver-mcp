{
  description = "Media Resolver MCP Server - MCP server for resolving and playing media via Mopidy";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;

        # Create a Python environment with all dependencies
        pythonEnv = python.withPackages (ps: with ps; [
          # Build tools
          pip
          setuptools
          wheel
        ]);

        # Build the media-resolver-mcp package using a wrapper script
        media-resolver-mcp = pkgs.stdenv.mkDerivation {
          pname = "media-resolver-mcp";
          version = "0.1.0";

          src = ./.;

          buildInputs = [ pythonEnv ];
          nativeBuildInputs = [ pkgs.makeWrapper ];

          # Don't unpack source automatically, we'll handle it
          dontUnpack = false;

          buildPhase = ''
            # Create a virtual environment and install the package
            export HOME=$TMPDIR
            ${pythonEnv}/bin/python -m venv $out/venv
            source $out/venv/bin/activate

            # Install the package and its dependencies
            pip install --no-cache-dir .
          '';

          installPhase = ''
            # Create bin directory
            mkdir -p $out/bin

            # Create wrapper script that activates venv and runs the app
            makeWrapper $out/venv/bin/media-resolver $out/bin/media-resolver \
              --prefix PATH : ${pkgs.lib.makeBinPath [ python ]}
          '';

          meta = with pkgs.lib; {
            description = "MCP server for resolving and playing media via Mopidy and Home Assistant";
            homepage = "https://github.com/yourusername/media-resolver-mcp";
            license = licenses.mit;
            maintainers = [ ];
            mainProgram = "media-resolver";
          };
        };

      in
      {
        # Package output
        packages = {
          default = media-resolver-mcp;
          media-resolver-mcp = media-resolver-mcp;
        };

        # App to run the MCP server
        apps = {
          default = {
            type = "app";
            program = "${media-resolver-mcp}/bin/media-resolver";
          };
          media-resolver = {
            type = "app";
            program = "${media-resolver-mcp}/bin/media-resolver";
          };
        };

        # Development shell with Python environment
        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
            pkgs.git
          ];

          shellHook = ''
            echo "Media Resolver MCP Server development environment"
            echo "Python version: ${python.version}"
            echo ""
            echo "To install the package in development mode:"
            echo "  pip install -e ."
            echo ""
            echo "To install with dev dependencies:"
            echo "  pip install -e \".[dev]\""
            echo ""
            echo "To run the server:"
            echo "  python -m media_resolver.server"
            echo "  # or after installing: media-resolver"
          '';
        };
      }
    );
}
