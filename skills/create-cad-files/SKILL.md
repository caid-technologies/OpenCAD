---
name: create-cad-files
description: Create dimensioned 3D CAD parts from natural-language requirements and export validated STEP, STP, or STL files with OpenCAD. Use when a user asks Claude or Codex to model a mechanical part, make a printable STL, create an editable STEP file, convert a dimensional description into CAD, or revise a previously generated OpenCAD model.
---

# Create CAD Files

Create the model as readable OpenCAD Python, export it with the native OCCT backend, and validate the exchange file before returning it. Keep the user experience prompt-first: handle source generation, build commands, and validation without asking the user to operate Python.

## Workflow

1. Extract dimensions, units, geometry, holes, clearances, and output format. Use millimeters unless specified otherwise. Ask only when a missing dimension materially changes the part; otherwise state the assumption.
2. Prefer STEP for editable/manufacturing geometry and STL for a triangulated 3D-printing deliverable. Create both when requested.
3. Read [references/opencad-api.md](references/opencad-api.md) before writing a model. Save the model source beside its artifacts in the user's workspace.
4. Keep the model parametric: assign important dimensions to named constants, create one final `Part`, and leave that final part as the last generated shape. Do not call `Part.export()` in the model; the build helper owns export and validation.
5. Ensure `opencad[occt]` is installed. If importing OpenCAD fails, explain the dependency and ask before installing it into the active Python environment.
6. Resolve this skill's directory, stay in the user's workspace, and run the helper by its absolute path:

   ```bash
   python /path/to/create-cad-files/scripts/build_cad_file.py MODEL.py OUTPUT.step --tree-output OUTPUT.tree.json
   ```

   Use an `.stl` output name for STL. The helper refuses to replace files unless `--force` is explicitly supplied.
7. If exporting both formats, run the same source twice. Validate an existing artifact independently with the absolute path to `scripts/validate_cad_file.py`.
8. Inspect failures and revise the source rather than bypassing validation. Return clickable paths for the source, CAD artifacts, and feature tree, plus units and assumptions.

## Quality rules

- Preserve exact requested dimensions and name user-facing parameters.
- Use closed, ordered sketch profiles. Avoid self-intersections, zero-thickness contact, and coplanar boolean ambiguity.
- Apply fillets and chamfers after the main solid and boolean operations.
- Keep holes and clearances explicit. Do not invent manufacturing tolerances; flag them when fit matters.
- Do not claim that basic file validation proves printability, load capacity, code compliance, or manufacturability.
- Retain the Python source and tree JSON so revisions remain reproducible.

## Failure handling

- If CadQuery/OCP is unavailable, use `opencad[occt]`; never substitute the analytic backend for a deliverable.
- If a boolean or fillet fails, simplify the feature, reduce the radius, or eliminate coincident faces.
- If requested geometry exceeds the API surface, explain the limitation and implement the closest faithful parametric model only with the user's agreement.
