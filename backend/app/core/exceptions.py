class ImageProcessingError(Exception):
    """Ошибка на этапе обработки изображения (processing/).

    Args:
        step: название шага, напр. "preprocess_image", "find_contours"
        message: детальное сообщение
    """
    def __init__(self, step: str, message: str) -> None:
        self.step = step
        super().__init__(f"[{step}] {message}")


class FloorPlanNotFoundError(Exception):
    """Реконструкция/план не найден в БД."""
    def __init__(self, reconstruction_id: int) -> None:
        self.reconstruction_id = reconstruction_id
        super().__init__(f"Reconstruction {reconstruction_id} not found")


class FileStorageError(Exception):
    """Файл не найден на диске или не читается."""
    def __init__(self, file_id: str, path: str) -> None:
        self.file_id = file_id
        super().__init__(f"File {file_id} not found at {path}")


class FloorTransitionNotFoundError(Exception):
    """Переход между этажами не найден в БД."""
    def __init__(self, transition_id: int) -> None:
        self.transition_id = transition_id
        super().__init__(f"FloorTransition {transition_id} not found")


class FloorTransitionError(Exception):
    """Ошибка бизнес-логики при работе с переходами."""
    pass


class NavGraphNotFoundError(Exception):
    """Nav-граф не найден на диске для данной реконструкции."""
    def __init__(self, reconstruction_id: int) -> None:
        self.reconstruction_id = reconstruction_id
        super().__init__(
            f"Nav graph not found for reconstruction {reconstruction_id}. Build nav graph first."
        )


# Building hierarchy exceptions


class BuildingNotFoundError(Exception):
    """Building not found in DB."""

    def __init__(self, building_id: int) -> None:
        self.building_id = building_id
        super().__init__(f"Building {building_id} not found")


class BuildingDuplicateCodeError(Exception):
    """Attempt to create a building with a code that is already taken."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Building with code '{code}' already exists")


class FloorNotFoundError(Exception):
    """Floor not found in DB."""

    def __init__(self, floor_id: int) -> None:
        self.floor_id = floor_id
        super().__init__(f"Floor {floor_id} not found")


class FloorDuplicateNumberError(Exception):
    """Attempt to create a floor with a number already used in this building."""

    def __init__(self, building_code: str, number: int) -> None:
        self.building_code = building_code
        self.number = number
        super().__init__(f"Floor {number} already exists in building {building_code}")


class SectionValidationError(Exception):
    """Payload validation error for section replace operation.

    Raised by SectionService._validate_payload for:
    - Duplicate section numbers within the payload
    - Duplicate reconstruction_id within the payload
    - Missing reconstruction (FK does not exist in DB)
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class FloorSchemaError(Exception):
    """Error related to floor schema image or pipeline.

    Raised by FloorSchemaService when:
    - schema_image_id is None and extract_walls is called
    - Image file is not found on disk
    - Any domain-level schema constraint is violated
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


# Floor-stitching exceptions


class SectionNotBoundError(Exception):
    """Section has no bound reconstruction (409)."""

    def __init__(self, section_id: int) -> None:
        self.section_id = section_id
        super().__init__(f"Section {section_id} is not bound to a reconstruction")


class PreviewNotFoundError(Exception):
    """Unknown or expired build preview handle (422)."""

    def __init__(self, glb_file_id: str) -> None:
        self.glb_file_id = glb_file_id
        super().__init__(f"No such preview '{glb_file_id}' — rebuild first")


class SectionNotFoundError(Exception):
    """Section not found in DB (404)."""

    def __init__(self, section_id: int) -> None:
        self.section_id = section_id
        super().__init__(f"Section {section_id} not found")


class FloorAssemblyConflictError(Exception):
    """Floor is not in a valid state for the requested assembly step (-> 409).

    Raised for floor-level preconditions: no sections bound to plans (solve),
    or no transformed sections yet (build — run solve-transforms first).
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class FloorNavGraphNotFoundError(Exception):
    """Floor nav graph JSON not built yet (route request -> 404).

    Message is RU to match the other floor-assembly error messages surfaced to the
    operator (round-2 decision). The router maps this type to 404 via str(exc).
    """

    def __init__(self, floor_id: int) -> None:
        self.floor_id = floor_id
        super().__init__(
            "Граф навигации не построен — запустите построение графа этажа"
        )
