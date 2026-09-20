"""Kernel coordination layer.

Geometry implementations live in ``opencad.kernel.core`` backends.  This
module keeps the public ``OpenCadKernel`` entry point stable while owning
cross-backend concerns such as assembly-mate state and topology selection.
"""

from __future__ import annotations

from typing import Any

from opencad.kinematics import evaluate_assembly_pose, evaluate_joint_pose
from opencad.kernel.core.analytic_backend import AnalyticBackend
from opencad.kernel.core.backend import KernelBackend
from opencad.kernel.core.errors import ErrorCode, make_failure
from opencad.kernel.core.models import (
    AssemblyMate,
    AssemblyMateStatus,
    KinematicJoint,
    MeshData,
    OperationResult,
    ShapeData,
    Success,
    TopologyMap,
)
from opencad.kernel.core.store import IdStrategy, JointStore, MateStore
from opencad.kernel.core.topology import select as topo_select
from opencad.kernel.operations.schemas import (
    BooleanInput,
    ChamferEdgesInput,
    CircularPatternInput,
    CreateAssemblyMateInput,
    CreateKinematicJointInput,
    CreateBoxInput,
    CreateConeInput,
    CreateCylinderInput,
    CreateSketchInput,
    CreateSphereInput,
    CreateTorusInput,
    DeleteAssemblyMateInput,
    DeleteKinematicJointInput,
    DraftInput,
    ExportStlInput,
    ExportStepInput,
    ExtrudeInput,
    FilletEdgesInput,
    ImportStepInput,
    ImportStlInput,
    EvaluateKinematicAssemblyInput,
    EvaluateKinematicJointInput,
    LinearPatternInput,
    ListAssemblyMatesInput,
    ListKinematicJointsInput,
    LoftInput,
    MirrorInput,
    OffsetShapeInput,
    RevolveInput,
    SelectorQuery,
    ShellInput,
    SweepInput,
    TranslateInput,
)


class OpenCadKernel:
    """Coordinate application state around a replaceable geometry backend.

    ``AnalyticBackend`` remains the compatibility default for lightweight
    in-process use.  Production callers can inject ``OcctBackend`` without
    introducing backend branches into this facade.
    """

    def __init__(
        self,
        tolerance: float = 1e-6,
        allow_partial_boolean: bool = False,
        id_strategy: IdStrategy = "uuid",
        backend: KernelBackend | None = None,
    ) -> None:
        self.tolerance = tolerance
        self.allow_partial_boolean = allow_partial_boolean
        self._backend: KernelBackend = backend or AnalyticBackend(
            tolerance=tolerance,
            allow_partial_boolean=allow_partial_boolean,
            id_strategy=id_strategy,
        )
        self.store = self._backend.store
        self.mate_store = MateStore(id_strategy=id_strategy)
        self.joint_store = JointStore(id_strategy=id_strategy)

    @property
    def backend(self) -> KernelBackend:
        return self._backend

    # Geometry methods are explicit so ownership stays searchable and typed.

    def create_box(self, payload: CreateBoxInput) -> OperationResult:
        return self._backend.create_box(payload)

    def create_cylinder(self, payload: CreateCylinderInput) -> OperationResult:
        return self._backend.create_cylinder(payload)

    def create_sphere(self, payload: CreateSphereInput) -> OperationResult:
        return self._backend.create_sphere(payload)

    def create_cone(self, payload: CreateConeInput) -> OperationResult:
        return self._backend.create_cone(payload)

    def create_torus(self, payload: CreateTorusInput) -> OperationResult:
        return self._backend.create_torus(payload)

    def translate(self, payload: TranslateInput) -> OperationResult:
        return self._backend.translate(payload)

    def boolean_union(self, payload: BooleanInput) -> OperationResult:
        return self._backend.boolean_union(payload)

    def boolean_cut(self, payload: BooleanInput) -> OperationResult:
        return self._backend.boolean_cut(payload)

    def boolean_intersection(self, payload: BooleanInput) -> OperationResult:
        return self._backend.boolean_intersection(payload)

    def fillet_edges(self, payload: FilletEdgesInput) -> OperationResult:
        return self._backend.fillet_edges(payload)

    def chamfer_edges(self, payload: ChamferEdgesInput) -> OperationResult:
        return self._backend.chamfer_edges(payload)

    def shell(self, payload: ShellInput) -> OperationResult:
        return self._backend.shell(payload)

    def draft(self, payload: DraftInput) -> OperationResult:
        return self._backend.draft(payload)

    def offset_shape(self, payload: OffsetShapeInput) -> OperationResult:
        return self._backend.offset_shape(payload)

    def create_sketch(self, payload: CreateSketchInput) -> OperationResult:
        return self._backend.create_sketch(payload)

    def extrude(self, payload: ExtrudeInput) -> OperationResult:
        return self._backend.extrude(payload)

    def revolve(self, payload: RevolveInput) -> OperationResult:
        return self._backend.revolve(payload)

    def sweep(self, payload: SweepInput) -> OperationResult:
        return self._backend.sweep(payload)

    def loft(self, payload: LoftInput) -> OperationResult:
        return self._backend.loft(payload)

    def linear_pattern(self, payload: LinearPatternInput) -> OperationResult:
        return self._backend.linear_pattern(payload)

    def circular_pattern(self, payload: CircularPatternInput) -> OperationResult:
        return self._backend.circular_pattern(payload)

    def mirror(self, payload: MirrorInput) -> OperationResult:
        return self._backend.mirror(payload)

    def import_step(self, payload: ImportStepInput) -> OperationResult:
        return self._backend.import_step(payload)

    def export_step(self, payload: ExportStepInput) -> OperationResult:
        return self._backend.export_step(payload)

    def import_stl(self, payload: ImportStlInput) -> OperationResult:
        return self._backend.import_stl(payload)

    def export_stl(self, payload: ExportStlInput) -> OperationResult:
        return self._backend.export_stl(payload)

    def tessellate(self, shape_id: str, deflection: float = 0.1) -> MeshData:
        return self._backend.tessellate(shape_id, deflection)

    def get_topology(self, shape_id: str) -> TopologyMap:
        return self._backend.get_topology(shape_id)

    def get_native_shape(self, shape_id: str) -> Any:
        return self._backend.get_native_shape(shape_id)

    def select_subshapes(self, shape_id: str, query: SelectorQuery) -> list:
        """Apply the shared selector language to backend topology data."""
        topology = self._backend.get_topology(shape_id)
        return topo_select(topology.faces + topology.edges, query)

    def _invalid_input(self, message: str) -> OperationResult:
        return make_failure(
            code=ErrorCode.INVALID_INPUT,
            message=message,
            suggestion="Review numeric inputs and try again.",
            failed_check="input_validation",
        )

    def _resolve_entity_shape(self, entity_ref: str) -> ShapeData | None:
        """Extract a shape ID from a reference such as ``box-0001:face:0``."""
        shape_id = entity_ref.split(":")[0] if ":" in entity_ref else entity_ref
        return self.store.get(shape_id)

    def create_assembly_mate(self, payload: CreateAssemblyMateInput) -> OperationResult:
        """Create a 3-D assembly mate between two entity references."""
        shape_a = self._resolve_entity_shape(payload.entity_a)
        if shape_a is None:
            return make_failure(
                code=ErrorCode.MATE_INVALID_REFERENCE,
                message=f"Entity reference '{payload.entity_a}' does not resolve to a known shape.",
                suggestion="Use a valid entity reference (e.g. 'box-0001:face:0').",
                failed_check="mate_entity_a_lookup",
            )

        shape_b = self._resolve_entity_shape(payload.entity_b)
        if shape_b is None:
            return make_failure(
                code=ErrorCode.MATE_INVALID_REFERENCE,
                message=f"Entity reference '{payload.entity_b}' does not resolve to a known shape.",
                suggestion="Use a valid entity reference (e.g. 'cylinder-0001:face:1').",
                failed_check="mate_entity_b_lookup",
            )

        if payload.type.value in ("distance", "angle") and payload.value is None:
            return self._invalid_input(
                f"Assembly mate type '{payload.type.value}' requires a numeric 'value'."
            )

        for mate in self.mate_store.by_entity(payload.entity_a):
            if mate.entity_b == payload.entity_b and mate.type == payload.type.value:
                return make_failure(
                    code=ErrorCode.MATE_DUPLICATE,
                    message=f"A '{payload.type.value}' mate already exists between these entities.",
                    suggestion="Delete the existing mate first or adjust its value.",
                    failed_check="mate_duplicate_check",
                )

        mate = AssemblyMate(
            id=self.mate_store.new_id(),
            type=payload.type.value,
            entity_a=payload.entity_a,
            entity_b=payload.entity_b,
            value=payload.value,
            status=AssemblyMateStatus.PENDING,
        )
        self.mate_store.add(mate)
        return Success(
            shape_id=None,
            shape=None,
            metadata={
                "operation": "create_assembly_mate",
                "mate_id": mate.id,
                "mate": mate.model_dump(),
            },
        )


    # Rigid kinematic joints are intentionally separate from assembly mates:
    # mates constrain geometry; joints define allowed degrees of freedom.

    def _would_create_joint_cycle(self, parent_shape_id: str, child_shape_id: str) -> bool:
        cursor = parent_shape_id
        visited: set[str] = set()
        while cursor not in visited:
            if cursor == child_shape_id:
                return True
            visited.add(cursor)
            parent_joint = self.joint_store.by_child(cursor)
            if parent_joint is None:
                return False
            cursor = parent_joint.parent_shape_id
        return True

    def create_kinematic_joint(self, payload: CreateKinematicJointInput) -> OperationResult:
        parent = self.store.get(payload.parent_shape_id)
        child = self.store.get(payload.child_shape_id)
        if parent is None:
            return make_failure(
                code=ErrorCode.JOINT_INVALID_REFERENCE,
                message=f"Parent shape '{payload.parent_shape_id}' was not found.",
                suggestion="Create or import the parent shape before creating the joint.",
                failed_check="joint_parent_lookup",
            )
        if child is None:
            return make_failure(
                code=ErrorCode.JOINT_INVALID_REFERENCE,
                message=f"Child shape '{payload.child_shape_id}' was not found.",
                suggestion="Create or import the child shape before creating the joint.",
                failed_check="joint_child_lookup",
            )

        existing_parent = self.joint_store.by_child(payload.child_shape_id)
        if existing_parent is not None:
            return make_failure(
                code=ErrorCode.JOINT_DUPLICATE_CHILD,
                message=(
                    f"Shape '{payload.child_shape_id}' already has parent joint "
                    f"'{existing_parent.id}'."
                ),
                suggestion="Delete the existing parent joint before re-parenting the shape.",
                failed_check="joint_single_parent",
            )

        if self._would_create_joint_cycle(payload.parent_shape_id, payload.child_shape_id):
            return make_failure(
                code=ErrorCode.JOINT_CYCLE,
                message="The requested kinematic joint would create a cycle.",
                suggestion="Use an acyclic parent/child joint tree.",
                failed_check="joint_cycle",
            )

        if payload.joint_id and self.joint_store.get(payload.joint_id) is not None:
            return self._invalid_input(
                f"Kinematic joint id '{payload.joint_id}' already exists."
            )

        joint = KinematicJoint(
            id=payload.joint_id or self.joint_store.new_id(),
            type=payload.type,
            parent_shape_id=payload.parent_shape_id,
            child_shape_id=payload.child_shape_id,
            axis=tuple(payload.axis),
            origin_mm=tuple(payload.origin_mm),
            lower_limit=float(payload.lower_limit),
            upper_limit=float(payload.upper_limit),
            label=payload.label,
            metadata=dict(payload.metadata),
        )
        self.joint_store.add(joint)
        return Success(
            metadata={
                "operation": "create_kinematic_joint",
                "joint_id": joint.id,
                "joint": joint.model_dump(mode="json"),
            }
        )

    def delete_kinematic_joint(self, payload: DeleteKinematicJointInput) -> OperationResult:
        if not self.joint_store.delete(payload.joint_id):
            return make_failure(
                code=ErrorCode.JOINT_NOT_FOUND,
                message=f"Kinematic joint '{payload.joint_id}' was not found.",
                suggestion="Use a joint_id returned by create/list kinematic joints.",
                failed_check="joint_lookup",
            )
        return Success(
            metadata={
                "operation": "delete_kinematic_joint",
                "joint_id": payload.joint_id,
            }
        )

    def list_kinematic_joints(self, payload: ListKinematicJointsInput) -> OperationResult:
        joints = (
            self.joint_store.by_shape(payload.shape_id)
            if payload.shape_id
            else self.joint_store.all()
        )
        return Success(
            metadata={
                "operation": "list_kinematic_joints",
                "joints": [joint.model_dump(mode="json") for joint in joints],
            }
        )

    def evaluate_kinematic_joint(self, payload: EvaluateKinematicJointInput) -> OperationResult:
        joint = self.joint_store.get(payload.joint_id)
        if joint is None:
            return make_failure(
                code=ErrorCode.JOINT_NOT_FOUND,
                message=f"Kinematic joint '{payload.joint_id}' was not found.",
                suggestion="Use a valid joint_id from list_kinematic_joints.",
                failed_check="joint_lookup",
            )
        pose = evaluate_joint_pose(joint, float(payload.progress))
        return Success(
            metadata={
                "operation": "evaluate_kinematic_joint",
                "pose": pose.model_dump(mode="json"),
            }
        )

    def evaluate_kinematic_assembly(
        self,
        payload: EvaluateKinematicAssemblyInput,
    ) -> OperationResult:
        known = set(self.joint_store.all_ids())
        unknown = sorted(set(payload.progress_by_joint) - known)
        if unknown:
            return self._invalid_input(
                f"Unknown kinematic joint progress key(s): {', '.join(unknown)}."
            )
        try:
            transforms = evaluate_assembly_pose(
                self.joint_store.all(),
                payload.progress_by_joint,
            )
        except ValueError as exc:
            return make_failure(
                code=ErrorCode.JOINT_CYCLE,
                message=str(exc),
                suggestion="Repair the kinematic joint tree before evaluating it.",
                failed_check="joint_graph_evaluation",
            )
        return Success(
            metadata={
                "operation": "evaluate_kinematic_assembly",
                "transforms": {
                    shape_id: transform.model_dump(mode="json")
                    for shape_id, transform in transforms.items()
                },
            }
        )

    def delete_assembly_mate(self, payload: DeleteAssemblyMateInput) -> OperationResult:
        """Remove an existing assembly mate."""
        if not self.mate_store.delete(payload.mate_id):
            return make_failure(
                code=ErrorCode.MATE_NOT_FOUND,
                message=f"Assembly mate '{payload.mate_id}' was not found.",
                suggestion="Use a valid mate_id from a previous create_assembly_mate call.",
                failed_check="mate_lookup",
            )
        return Success(
            shape_id=None,
            shape=None,
            metadata={"operation": "delete_assembly_mate", "mate_id": payload.mate_id},
        )

    def list_assembly_mates(self, payload: ListAssemblyMatesInput) -> OperationResult:
        """List mates, optionally filtered by entity involvement."""
        mates = (
            self.mate_store.by_entity(payload.entity_ref)
            if payload.entity_ref
            else self.mate_store.all()
        )
        return Success(
            shape_id=None,
            shape=None,
            metadata={
                "operation": "list_assembly_mates",
                "mates": [mate.model_dump() for mate in mates],
            },
        )
