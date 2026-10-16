# OpenSC4
Godot clone of SimCity4

## Setup

1. Acquire Godot
2. Acquire and install Simcity 4 (preferably the Deluxe Edition)
3. Drop all the contents of the Simcity 4 install into the main project directory
   (they stay local — `.gitignore` keeps game files out of the repo)

## Roadmap

- [ ] Load proprietary assets from the game data
	- [x] Load images and textures
	- [ ] Load fonts
	- [ ] Load 3D models
	- [ ] Load sounds
- [ ] Clone the region screen
    - [x] Load all files in a region folder
    - [x] Display the city thumbnails
    - [ ] Display all city information when clicking on their thumbnail
    - [ ] Decoration (clouds and background grid)
    - [x] Play music
    - [ ] Add functionality to buttons
	- [ ] Region UI
		- [x] Display the basic elements of the region UI
		- [ ] Functional Region UI
			- [ ] Change settings from the UI
			- [ ] Exit from the UI
			- [ ] City prompts
			- [ ] Region management
- [ ] Clone the city screen
	- [ ] City UI
		- [ ] Cheat box input
		- [ ] Display the bottom right info
		- [ ] Functional God Mode -> Mayor Mode transition
		- [ ] Display the tools bar and its menus
		- [ ] City info display (graphs, budget, etc)
		- [ ] Lama advisors
    - [x] Render the terrain
    - [ ] Render the flora, fauna and buildings
    - [ ] Implement God tools
    - [ ] Implement mayor tools
    - [ ] City simulation
    - [ ] Play music
- [ ] Multiplayer integration
- [ ] Modding

## Developer documentation

- [Project status](docs/project-status.md)
- [Roadmap and milestones](docs/roadmap.md)
- [Architecture and simulation seams](docs/architecture.md)
- [Edge-case matrix](docs/edge-cases.md)
- [Behavioral compatibility lab](docs/simulation-lab.md)
- [Baseline runbook](docs/runbooks/baseline.md)
- [Performance runbook](docs/runbooks/performance.md)
- [Reference-lab runbook](docs/runbooks/reference-lab.md)
- [OpenGlassBox bridge runbook](docs/runbooks/openglassbox-bridge.md)
- [Development iteration and Git sync](docs/runbooks/iteration.md)
- [Future work and wishlist](docs/future-work.md)
- [Baseline milestone report](docs/milestones/lab-baseline-v0.2.md)

Quick local baseline:

```sh
bash tools/run_baseline.sh
```

Release/data-boundary check:

```sh
bash tools/check_data_boundary.sh
```

## License

GNU Affero General Public License v3.0 or later — see `LICENSE`.
