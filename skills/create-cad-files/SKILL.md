---
name: create-cad-files
description: Create dimensioned 3D CAD parts from natural-language requirements and export validated STEP, STP, or STL files with OpenCAD. Use when a user asks an AI agent to model a mechanical part, make a printable STL, create an editable STEP file, convert a dimensional description into CAD, or revise a previously generated OpenCAD model.
---

# Create CAD Files

Create the model as readable OpenCAD Python, export it with the native OCCT backend, and validate the exchange file before returning it. Keep the user experience prompt-first: handle source generation, build commands, and validation without asking the user to operate Python.

## Workflow

1. Extract dimensions, units, geometry, holes, clearances, and output format. Use millimeters unless specified otherwise. Ask only when a missing dimension materially changes the part; otherwise state the assumption.
2. Prefer STEP for editable/manufacturing geometry and STL for a triangulated 3D-printing deliverable. Create both when requested.
3. Read [references/opencad-api.md](references/opencad-api.md) before writing a model. At the start of every run, create a fresh project directory with `scripts/create_project.py` and use the returned path as `PROJECT_DIR`. The helper creates a UUID-named directory under `~/forma-workspace/`; never derive the project ID from the request. Keep every source file, README, component, and generated artifact inside `PROJECT_DIR`. Create `README.md` for project context, `assembly.py` as the master composition entry point, `parameters.py` when dimensions are shared, a `components/` Python package for component modules, and an `outputs/` directory for generated artifacts. Honor explicitly requested filenames inside `PROJECT_DIR`, but do not replace the shared root or generated project ID.
4. Keep the model parametric: assign important dimensions to named constants, have component modules expose named builders or parts, and create one final `Part` in `assembly.py`. Leave that final part as the last generated shape in `assembly.py` (or the explicitly requested master file). Do not call `Part.export()` in the model; the build helper owns export and validation.
5. Ensure `opencad[occt]` is installed. If importing OpenCAD fails, explain the dependency and ask before installing it into the active Python environment.
6. Resolve this skill's directory, create the project directory by its absolute path, stay inside the returned project directory, and run the build helper by its absolute path:

   ```bash
   PROJECT_DIR=$(python /path/to/create-cad-files/scripts/create_project.py)
   python /path/to/create-cad-files/scripts/build_cad_file.py "$PROJECT_DIR/assembly.py" "$PROJECT_DIR/outputs/assembly.step" --tree-output "$PROJECT_DIR/outputs/assembly.tree.json"
   ```

   Use an `.stl` output name for STL. The helper refuses to replace files unless `--force` is explicitly supplied.
7. If exporting both formats, run the same project `assembly.py` source twice. Validate an existing artifact independently with the absolute path to `scripts/validate_cad_file.py`.
8. Inspect failures and revise the source rather than bypassing validation. Return clickable paths for the source, CAD artifacts, and feature tree, plus units and assumptions.

## Quality rules

- Preserve exact requested dimensions and name user-facing parameters.
- Use closed, ordered sketch profiles. Avoid self-intersections, zero-thickness contact, and coplanar boolean ambiguity.
- Apply fillets and chamfers after the main solid and boolean operations.
- Keep holes and clearances explicit. Do not invent manufacturing tolerances; flag them when fit matters.
- Do not claim that basic file validation proves printability, load capacity, code compliance, or manufacturability.
- Retain the project source, `README.md`, and tree JSON so revisions remain reproducible.
- Keep the project self-contained so `assembly.py`, nested component packages, and generated artifacts can be managed together.
- Use `__init__.py` files for component packages and subpackages. Import nested components from the project root, for example `from components.motor.mount.screw_pattern import make_screw_pattern`.
- Document the project purpose, units, assumptions, key dimensions, component/package tree, build command, artifacts, and known limitations in `README.md`.

## Failure handling

- If CadQuery/OCP is unavailable, use `opencad[occt]`; never substitute the analytic backend for a deliverable.
- If a boolean or fillet fails, simplify the feature, reduce the radius, or eliminate coincident faces.
- If requested geometry exceeds the API surface, explain the limitation and implement the closest faithful parametric model only with the user's agreement.
