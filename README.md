# OSSA - Optimal Spatial Sampling Algorithm

## About

OSSA is a set of algorithms developed for spatial sampling designs in absence of any prior information about the process, such as species distribution or a disease prevalence (lattice with close pairs) and for adaptive sampling designs (when prior information is available). It also contains an algorithm for ecological area delineation.

TODO: This is a User Friendly Shiny App for the Optimal Spatial Sampling Algorithm (OSSA). The app allows users to easily implement OSSA for spatial sampling designs and ecological area delineation without needing interact directly with R code.

## Installation & Running

- Docker




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
