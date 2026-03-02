# OSSA

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

## macOS Installation & Running

1. Download the latest release zip
2. Extract the zip file
3. Right-click the app and select "Open"
4. Click "Open" in the security dialog

Or in Terminal:
```bash
xattr -d com.apple.quarantine /path/to/lancs-leeg-ossa.app
```
