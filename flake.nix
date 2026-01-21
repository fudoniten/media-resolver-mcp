{
  description = "Media Resolver MCP Server - A Model Context Protocol server for Home Assistant media playback";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
        pythonPackages = python.pkgs;

        media-resolver-mcp = pythonPackages.buildPythonApplication {
          pname = "media-resolver-mcp";
          version = "0.1.0";
          pyproject = true;

          src = ./.;

          nativeBuildInputs = with pythonPackages; [
            setuptools
            wheel
          ];

          propagatedBuildInputs = with pythonPackages; [
            # MCP Server Framework
            fastmcp

            # Web Framework for Admin UI
            fastapi
            uvicorn
            jinja2

            # LangChain for LLM integration
            langchain
            langchain-core
            langchain-community
            # Note: langchain-anthropic and langchain-openai may need to be added
            # if they become available in nixpkgs

            # HTTP clients
            httpx
            aiohttp

            # Configuration and data handling
            pydantic
            pydantic-settings
            pyyaml

            # RSS parsing for podcasts
            feedparser
            python-dateutil

            # Utilities
            python-dotenv
            structlog
          ];

          # Optional dependencies for development
          passthru.optional-dependencies = {
            dev = with pythonPackages; [
              pytest
              pytest-asyncio
              pytest-cov
              pytest-mock
              black
              ruff
              mypy
            ];
          };

          # Don't run tests during build (they require external services)
          doCheck = false;

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
        packages = {
          default = media-resolver-mcp;
          media-resolver-mcp = media-resolver-mcp;
        };

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

        # Development shell with all dependencies
        devShells.default = pkgs.mkShell {
          buildInputs = [
            media-resolver-mcp
            python
          ] ++ (with pythonPackages; [
            pytest
            pytest-asyncio
            pytest-cov
            pytest-mock
            black
            ruff
            mypy
          ]);

          shellHook = ''
            echo "Media Resolver MCP Development Environment"
            echo "==========================================="
            echo "Available commands:"
            echo "  media-resolver  - Run the MCP server"
            echo "  pytest          - Run tests"
            echo "  black           - Format code"
            echo "  ruff            - Lint code"
            echo ""
            echo "Make sure to configure config/config.yaml and .env before running!"
          '';
        };
      }
    );
}
