"""
Tests for tasks API endpoints.
"""
import pytest

from mock_data import tasks as tasks_store


@pytest.fixture(autouse=True)
def reset_tasks():
    """Keep the in-memory task list isolated between tests.

    main.py imports the same list object from mock_data, so mutating it in
    place here is what the endpoints see.
    """
    saved = list(tasks_store)
    tasks_store[:] = []
    yield
    tasks_store[:] = saved


@pytest.fixture
def new_task_payload():
    """Payload matching what TasksModal.vue emits."""
    return {
        "title": "Audit Q1 stock levels",
        "dueDate": "2026-01-15",
        "priority": "high"
    }


class TestTasksEndpoints:
    """Test suite for task-related endpoints."""

    def test_get_all_tasks_empty(self, client):
        """Test getting tasks when none have been created."""
        response = client.get("/api/tasks")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert data == []

    def test_create_task(self, client, new_task_payload):
        """Test creating a task."""
        response = client.post("/api/tasks", json=new_task_payload)
        assert response.status_code == 200

        task = response.json()
        assert task["title"] == new_task_payload["title"]
        assert task["dueDate"] == new_task_payload["dueDate"]
        assert task["priority"] == new_task_payload["priority"]
        assert task["status"] == "pending"
        assert "id" in task

    def test_created_task_id_is_a_string(self, client, new_task_payload):
        """Task ids must be strings.

        App.vue merges API tasks with per-user mock tasks that use integer
        ids 1..4, and tells them apart by id equality. An integer id here
        would make delete/toggle act on the wrong task.
        """
        response = client.post("/api/tasks", json=new_task_payload)
        task = response.json()

        assert isinstance(task["id"], str)
        assert task["id"] not in ("1", "2", "3", "4")

    def test_create_task_defaults_priority(self, client):
        """Test that priority defaults to medium when omitted."""
        response = client.post(
            "/api/tasks",
            json={"title": "Reorder connectors", "dueDate": "2026-02-01"}
        )
        assert response.status_code == 200
        assert response.json()["priority"] == "medium"

    def test_create_task_requires_title_and_due_date(self, client):
        """Test validation of required fields."""
        assert client.post("/api/tasks", json={"dueDate": "2026-02-01"}).status_code == 422
        assert client.post("/api/tasks", json={"title": "No date"}).status_code == 422

    def test_created_task_appears_in_list(self, client, new_task_payload):
        """Test that a created task is returned by the list endpoint."""
        created = client.post("/api/tasks", json=new_task_payload).json()

        response = client.get("/api/tasks")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == created["id"]

    def test_create_multiple_tasks_get_unique_ids(self, client, new_task_payload):
        """Test that ids do not collide across tasks."""
        ids = {
            client.post("/api/tasks", json=new_task_payload).json()["id"]
            for _ in range(5)
        }
        assert len(ids) == 5

    def test_toggle_task_marks_completed(self, client, new_task_payload):
        """Test toggling a pending task to completed."""
        created = client.post("/api/tasks", json=new_task_payload).json()

        response = client.patch(f"/api/tasks/{created['id']}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_toggle_task_is_reversible(self, client, new_task_payload):
        """Test that toggling twice returns the task to pending."""
        created = client.post("/api/tasks", json=new_task_payload).json()

        client.patch(f"/api/tasks/{created['id']}")
        response = client.patch(f"/api/tasks/{created['id']}")

        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    def test_toggle_task_persists(self, client, new_task_payload):
        """Test that a toggled status is reflected in the list endpoint."""
        created = client.post("/api/tasks", json=new_task_payload).json()
        client.patch(f"/api/tasks/{created['id']}")

        data = client.get("/api/tasks").json()
        assert data[0]["status"] == "completed"

    def test_delete_task(self, client, new_task_payload):
        """Test deleting a task."""
        created = client.post("/api/tasks", json=new_task_payload).json()

        response = client.delete(f"/api/tasks/{created['id']}")
        assert response.status_code == 200
        assert response.json()["success"] is True

        assert client.get("/api/tasks").json() == []

    def test_delete_only_removes_the_named_task(self, client, new_task_payload):
        """Test that deleting one task leaves the others alone."""
        keep = client.post("/api/tasks", json=new_task_payload).json()
        remove = client.post("/api/tasks", json=new_task_payload).json()

        client.delete(f"/api/tasks/{remove['id']}")

        remaining = client.get("/api/tasks").json()
        assert [t["id"] for t in remaining] == [keep["id"]]

    def test_toggle_nonexistent_task(self, client):
        """Test toggling a task that doesn't exist."""
        response = client.patch("/api/tasks/task-does-not-exist")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_delete_nonexistent_task(self, client):
        """Test deleting a task that doesn't exist."""
        response = client.delete("/api/tasks/task-does-not-exist")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_task_structure(self, client, new_task_payload):
        """Test that a task has all required fields with correct types."""
        client.post("/api/tasks", json=new_task_payload)

        task = client.get("/api/tasks").json()[0]

        for field in ("id", "title", "priority", "dueDate", "status"):
            assert field in task
            assert isinstance(task[field], str)

    def test_task_status_values(self, client, new_task_payload):
        """Test that status is constrained to the values the UI understands."""
        created = client.post("/api/tasks", json=new_task_payload).json()
        assert created["status"] in ("pending", "completed")

        toggled = client.patch(f"/api/tasks/{created['id']}").json()
        assert toggled["status"] in ("pending", "completed")

    def test_due_date_is_camel_case(self, client, new_task_payload):
        """Test the dueDate field name.

        TasksModal.vue reads task.dueDate for both API tasks and the
        localized mock tasks, so this field must not be snake_cased.
        """
        task = client.post("/api/tasks", json=new_task_payload).json()

        assert "dueDate" in task
        assert "due_date" not in task
