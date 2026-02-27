# OSSA

## Dependencies
- Python >= 3.13
- R >= 4.3

## Setup





## Development

- Ensure Poetry is installed.
- Run `poetry install` to install dependencies.
- Run `poetry run shiny run app.py` to start the app.
- To debug the Shiny app in Visual Studio Code and localhost (e.g. http://127.0.0.1:8000/), you can use the following `launch.json` configuration:
```
{
    "version": "0.2.0",
    "configurations": [

        {
            "name": "Debug Shiny App",
            "type": "debugpy",
            "request": "launch",
            "module": "shiny",
            "args": ["run", "--reload", "app.py"],
            "console": "integratedTerminal",
            "justMyCode": false,
            "cwd": "${workspaceFolder}"
        }
    ]
}
```

- Uses `poetry run flake8` for linting.
- Uses `poetry run black app.py` to format the code.
- Run on all files: `poetry run pre-commit run --all-files`
