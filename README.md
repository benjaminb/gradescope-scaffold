# Customizable Autograder For Gradescope Python Projects

## The Problem

I developed this autograder while working for Harvard's CS1 course to streamline creating and deploying unit tests for student Python programming assignments on Gradescope. Unit tests are a great way to provide students with immediate feedback on their code. It also allows course staff to spend more time providing individualized feedback rather than pointing out common mistakes.

I encountered two main challenges while building out CS1's codebase, which this project resolves: Gradescope runs an old Python version by default, and test development and validation was too cumbersome.

1. Most students are using the current version of Python (3.13 as of late 2025) but Gradescope runs in Python 3.10 by default. This causes even some simple programs to fail due to features in newer Python versions, such as quotes in f-strings and how dict keys get ordered.
1. Developing and validating tests should happen in the same environment in which the tests will run, which requires using Gradescope's autograder base image. To use this correctly (and with Python 3.13) takes a lot of setup.

## The Solution

This project provides a highly efficient `Dockerfile` that builds assignments with Python 3.13, pulling assignment files from a simple, easy-to-manage folder structure.

Features:

1. Upgrades Python to 3.13 in the [Gradescope Autograder Base Image](https://gradescope-autograders.readthedocs.io/en/latest/base_images/), so it matches what most students are using
1. Provides a `Dockerfile` that efficiently builds custom autograder images: rarely changing layers (common files) build before frequently changing layers (assignment-specific files) so rebuilds are typically very fast
1. Allows you to easily create assignment autograders, manage test files, and add supporting data files
1. Allows you to easily manage common support files shared across all assignments

## Usage

### Project Structure

```
your-course-or-project/
├── .dockerignore (optional)
├── .env (optional)
├── .gitignore (optional)
├── Dockerfile
├── common/
│   ├── source/
│   │   ├── requirements.txt
│   │   └── run_tests.py
│   └── tests/
│       └── <supporting dirs/files for all assignments>
├── hw1/
│   ├── test*.py
│   └── <hw1-specific supporting dirs/files>
└── hw2/
    ├── test*.py
    └── <hw2-specific supporting dirs/files>
```

### Building and Deploying the Docker Image

1. Create a folder for your assignment in the project root (e.g., `hw1`)
1. Place any `test*.py` files inside that folder to define your tests, along with any supporting files the tests may need
1. In `common/source/`, add any files that you'll want placed in all assignments' `source/` directories (e.g. `requirements.txt`)
1. In `common/tests/`, add any support files you'll want placed adjacent to all assignments' tests, such as supporting data files or helper modules.
1. Make sure the following files are present in the project root:

   - `Dockerfile`
   - `.env` (optional: for any environment variables you want passed into the image, such as API keys)
   - `.dockerignore` (optional: describes files to exclude from the image Docker will build)
     Run the following command to build the Docker image, replacing `hw1` with your assignment's folder name and `your-image-name` with your desired image name:

   ```sh
   docker build \
   --build-arg BASE_REPO=gradescope/autograder-base \
   --build-arg TAG=latest \
   --build-arg ASSIGNMENT=hw1 \
   -t your-image-name .
   ```

   If you are using a `.env` file, add the following to the command above:

   ```sh
   --secret id=.env,src=./.env \
   ```

   I use `--secret` instead of `--env-file` to avoid publishing private API keys in image layers, which may be publicly viewable if you push the image to a registry like Docker Hub.

1. Deploy to Docker Hub (`docker push your-image-repo-name/your-image-name`) or your preferred container registry.

## Future Additions

When time permits, I'll be adding the following features from my private codebase:

- A script to automate building images
- Support for sample assignments and a script to run the autograders against them locally
- A helper module providing classes and functions that help analyze code submissions:
  - Validating presence and signatures of required functions
  - Providing stdin and capturing stdout for testing interactive programs
  - Capturing the AST for static analysis of student code
  - LLM-calling functions
