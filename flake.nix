{
  description = "Media Resolver MCP Server - A Model Context Protocol server for Home Assistant media playback";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    
    # LangChain provider packages not yet in nixpkgs
    langchain-openai-src = {
      url = "https://files.pythonhosted.org/packages/38/b7/30bfc4d1b658a9ee524bcce3b0b2ec9c45a11c853a13c4f0c9da9882784b/langchain_openai-1.1.7.tar.gz";
      flake = false;
    };
    langchain-anthropic-src = {
      url = "https://files.pythonhosted.org/packages/0d/b6/ac5ee84e15bf79844c9c791f99a614c7ec7e1a63c2947e55977be01a81b4/langchain_anthropic-1.3.1.tar.gz";
      flake = false;
    };
  };

  outputs = { self, nixpkgs, flake-utils, langchain-openai-src, langchain-anthropic-src }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
        pythonPackages = python.pkgs;

        # Custom package for langchain-openai using flake input
        langchain-openai = pythonPackages.buildPythonPackage rec {
          pname = "langchain-openai";
          version = "1.1.7";
          pyproject = true;

          src = langchain-openai-src;

          build-system = with pythonPackages; [
            poetry-core
          ];

          dependencies = with pythonPackages; [
            langchain-core
            openai
            tiktoken
          ];

          pythonImportsCheck = [ "langchain_openai" ];

          doCheck = false; # Skip tests to avoid additional dependencies
        };

        # Custom package for langchain-anthropic using flake input
        langchain-anthropic = pythonPackages.buildPythonPackage rec {
          pname = "langchain-anthropic";
          version = "1.3.1";
          pyproject = true;

          src = langchain-anthropic-src;

          build-system = with pythonPackages; [
            poetry-core
          ];

          dependencies = with pythonPackages; [
            anthropic
            langchain-core
            pydantic
          ];

          pythonImportsCheck = [ "langchain_anthropic" ];

          doCheck = false; # Skip tests to avoid additional dependencies
        };

        media-resolver-mcp = pythonPackages.buildPythonApplication {
          pname = "media-resolver-mcp";
          version = "0.1.0";
          pyproject = true;

          src = ./.;

          nativeBuildInputs = with pythonPackages; [
            setuptools
            wheel
          ];

          propagatedBuildInputs = [
            # MCP Server Framework
            pythonPackages.fastmcp

            # Web Framework for Admin UI
            pythonPackages.fastapi
            pythonPackages.uvicorn
            pythonPackages.jinja2

            # LangChain for LLM integration
            pythonPackages.langchain
            pythonPackages.langchain-core
            pythonPackages.langchain-community
            langchain-anthropic  # Custom package
            langchain-openai     # Custom package

            # HTTP clients
            pythonPackages.httpx
            pythonPackages.aiohttp

            # Configuration and data handling
            pythonPackages.pydantic
            pythonPackages.pydantic-settings
            pythonPackages.pyyaml

            # RSS parsing for podcasts
            pythonPackages.feedparser
            pythonPackages.python-dateutil

            # Utilities
            pythonPackages.python-dotenv
            pythonPackages.structlog
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
