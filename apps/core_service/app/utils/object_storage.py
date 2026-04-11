def build_source_object_key(task_id: int, file_name: str) -> str:
    sanitized_file_name = file_name.replace("\\", "/").split("/")[-1].strip()
    if not sanitized_file_name:
        sanitized_file_name = "upload.bin"
    return f"tasks/{task_id}/source/{sanitized_file_name}"


def build_content_list_object_key(task_id: int) -> str:
    return f"tasks/{task_id}/content_list.json"


def build_logical_tables_object_key(task_id: int) -> str:
    return f"tasks/{task_id}/logical_tables.json"
