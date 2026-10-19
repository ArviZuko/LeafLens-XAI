# Windows installer

Download [installer.exe](https://github.com/ArviZuko/LeafLens-XAI/releases/download/project-assets-v1/installer.exe) from the [project Release](https://github.com/ArviZuko/LeafLens-XAI/releases/tag/project-assets-v1).

The public installer is rebuilt from the supplied app using `installer-public.iss`, which uses this repository's paths and excludes local `.env` credentials. `installer.iss` preserves the original build recipe. The original local installer is not published because its recipe bundles the runtime without excluding environment files. The installed application retains the original PlantDiseaseAI branding.
