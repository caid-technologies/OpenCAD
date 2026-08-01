# OpenCAD Examples

These examples show how to use the in-process OpenCAD API to model parts that commonly
appear in collaborative device-development work across hardware, software, and firmware
teams.

## Included scripts

- `hardware_mounting_bracket.py` — mechanical mounting bracket with fastener holes
- `hardware_pcb_carrier.py` — carrier plate for a controller or sensor PCB
- `software_hmi_panel.py` — front panel for a software-driven operator interface
- `firmware_programmer_fixture.py` — fixture plate for firmware flashing or debug access
- `full_device_cable_grommet.py` — cable-management part built from primitive booleans
- `simcorrect_forearm_design.py` — CAID design artifact for SimCorrect Problem 1

## Running an example

Install the native geometry backend and run from the repository root:

```bash
uv sync --extra occt
python -m opencad.cli run examples/hardware_mounting_bracket.py \
  --export bracket.step \
  --tree-output bracket-tree.json
```

Each modeling script leaves the final part in the default runtime context, so the CLI can
export both a STEP file and a serialized feature tree.

To generate the SimCorrect Problem 1 handoff artifact:

```bash
uv run --no-sync python examples/simcorrect_forearm_design.py
```

This writes `caid-design.json` with `forearm_length` mapped to the MuJoCo parameter
`link2_length`.
