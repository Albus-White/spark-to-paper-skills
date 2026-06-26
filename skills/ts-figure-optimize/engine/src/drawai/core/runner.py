from __future__ import annotations

from collections.abc import Callable, Iterable

from .context import RunContext
from .errors import StageFailure
from .stage import StageResult, StageSpec

BeforeStageHook = Callable[[StageSpec], None]
AfterStageHook = Callable[[StageSpec, StageResult], None]


class DagRunner:
    def __init__(self, stages: Iterable[StageSpec]) -> None:
        stage_list = list(stages)
        if len(stage_list) == 0:
            raise ValueError("DagRunner requires at least one stage")
        stage_ids = [stage.stage_id for stage in stage_list]
        duplicate_stage_ids = sorted({stage_id for stage_id in stage_ids if stage_ids.count(stage_id) > 1})
        if duplicate_stage_ids:
            raise ValueError(f"duplicate stage id: {', '.join(duplicate_stage_ids)}")
        self._stages = {stage.stage_id: stage for stage in stage_list}
        self._validate_dependencies()

    def run(
        self,
        context: RunContext,
        *,
        before_stage: BeforeStageHook | None = None,
        after_stage: AfterStageHook | None = None,
    ) -> list[StageResult]:
        results: list[StageResult] = []
        for stage in self.topological_order():
            if before_stage is not None:
                before_stage(stage)
            self._validate_provider_contract(context, stage)
            result = stage.run(context)
            if result.stage_id != stage.stage_id:
                raise StageFailure(
                    stage.stage_id,
                    f"stage returned result for {result.stage_id!r}",
                    contract="result",
                    details={"result_stage_id": result.stage_id},
                )
            if stage.validate is not None:
                stage.validate(context, result)
            self._validate_output_contract(stage, result)
            if after_stage is not None:
                after_stage(stage, result)
            results.append(result)
        return results

    def topological_order(self) -> list[StageSpec]:
        ordered: list[StageSpec] = []
        temporary: set[str] = set()
        permanent: set[str] = set()

        def visit(stage_id: str) -> None:
            if stage_id in permanent:
                return
            if stage_id in temporary:
                raise ValueError(f"stage dependency cycle includes {stage_id!r}")
            temporary.add(stage_id)
            stage = self._stages[stage_id]
            for dependency in stage.depends_on:
                visit(dependency)
            temporary.remove(stage_id)
            permanent.add(stage_id)
            ordered.append(stage)

        for stage_id in self._stages:
            visit(stage_id)
        return ordered

    def _validate_dependencies(self) -> None:
        for stage in self._stages.values():
            for dependency in stage.depends_on:
                if dependency not in self._stages:
                    raise ValueError(f"stage {stage.stage_id!r} depends on unknown stage {dependency!r}")

    @staticmethod
    def _validate_provider_contract(context: RunContext, stage: StageSpec) -> None:
        missing = [
            provider.name
            for provider in stage.providers
            if provider.required and provider.name not in context.providers
        ]
        if missing:
            raise StageFailure(
                stage.stage_id,
                f"missing providers: {', '.join(missing)}",
                contract="providers",
                details={"missing": missing},
            )

    @staticmethod
    def _validate_output_contract(stage: StageSpec, result: StageResult) -> None:
        missing = [artifact_id for artifact_id in stage.outputs if artifact_id not in result.artifacts]
        if missing:
            raise StageFailure(
                stage.stage_id,
                f"missing output artifacts: {', '.join(missing)}",
                contract="outputs",
                details={"missing": missing},
            )
        missing_files = [
            artifact_id
            for artifact_id in stage.outputs
            if not result.artifacts[artifact_id].exists
        ]
        if missing_files:
            raise StageFailure(
                stage.stage_id,
                f"output artifact files are missing: {', '.join(missing_files)}",
                contract="outputs",
                details={"missing_files": missing_files},
            )
