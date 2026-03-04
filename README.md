# OSSA - Optimal Spatial Sampling Algorithm

## About

OSSA is a set of algorithms developed for spatial sampling designs in absence of any prior information about the process, such as species distribution or a disease prevalence (lattice with close pairs) and for adaptive sampling designs (when prior information is available). It also contains an algorithm for ecological area delineation.

TODO: This is a User Friendly Shiny App for the Optimal Spatial Sampling Algorithm (OSSA). The app allows users to easily implement OSSA for spatial sampling designs and ecological area delineation without needing interact directly with R code.

## Installation & Running

OSSA runs locally on your machine using Docker. To get started, follow these steps:
1. Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop/). You will only need to do this once.
2. run the launch script:

   - For a Mac it is the ```launch.sh``` so in ther terminal ```sh <PATH>/launch.sh```
   - For a PC it is the ```launch.bat``` so in the command prompt ```<PATH>\launch.bat```

3. Open your web browser and navigate to ```http://0.0.0.0:8000```
4. OSSA will be ready to use!
5. Downloads can be found from Docker Desktop:
    - Click on three dots icon > show container actions > View files.
    - Any downloads will be in, ```app > output```
    - Right-click on the file you want to download and select "Save". The file will be downloaded to your local machine.
6. You will also see the container running in Docker Desktop. You can stop the container when you are done using OSSA.

## Report an Issue

To report a bug, crash, or unexpected behavior etc, please copy the log messages from Docker
1. Click on three dots icon > show container actions > Use Docker Debug
2. Switch to the "Logs" tab and copy the log messages.

## Development

### VS Code & Poetry
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

### Docker
- To debug in Docker ```docker compose up --build```
- Then Ctrl + C to stop the container and run ```docker compose down``` to clean up.

- The above is useful for a quick test if there are only small code changes. To force a total rebuild, including all R and Python environments:
```
docker compose down -v
docker compose build --no-cache
docker compose up
```

## Deployment

To create a new docker image on GitHub:

```commandline
git tag v0.0.1
git push origin v0.0.1
```
