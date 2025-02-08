from asgiref.sync import sync_to_async
from django.db import models
from django.shortcuts import render
from ksuid import Ksuid
from nanodjango import Django
from openai import OpenAI
import asyncio
import docker
import json

app = Django(
    # ALLOWED_HOSTS=["localhost", "127.0.0.1"],
    # SECRET_KEY=os.environ["SECRET_KEY"],
    # DEBUG=False,
)

### Models


class KSUIDField(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 27  # Base62 KSUID length
        kwargs["unique"] = True
        super().__init__(*args, **kwargs)

    def pre_save(self, model_instance, add):
        if add and not getattr(model_instance, self.attname):
            # Generate new KSUID and convert to string
            value = str(Ksuid())
            setattr(model_instance, self.attname, value)
            return value
        return super().pre_save(model_instance, add)


class Settings(models.Model):
    key = models.CharField(max_length=255)
    value = models.TextField()


class Thread(models.Model):
    id = KSUIDField(primary_key=True)
    thread_name = models.CharField(max_length=255)
    state = models.CharField(max_length=255, default="idle")
    created_on = models.DateTimeField(auto_now_add=True)
    edited_on = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)


class Log(models.Model):
    id = KSUIDField(primary_key=True)
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="logs")
    sender = models.CharField(max_length=255)
    type = models.CharField(max_length=100)
    payload = models.TextField()
    created_on = models.DateTimeField(auto_now_add=True)
    edited_on = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)


### Agent logic


async def create_container(thread_id: str, docker_client):
    container_name = f"{thread_id}_wandb"
    try:
        container = docker_client.containers.get(container_name)
    except docker.errors.NotFound:
        # Ensure network exists
        network_name = "wandb_network"
        try:
            network = docker_client.networks.get(network_name)
        except docker.errors.NotFound:
            network = docker_client.networks.create(network_name)

        # Create container
        container = docker_client.containers.run(
            image="code-runner-client",
            name=container_name,
            shm_size="512mb",
            restart_policy={"Name": "unless-stopped"},
            network=network_name,
            detach=True,
            command=["/bin/sh", "-c", "sleep infinity"],
        )
        await asyncio.sleep(3)

    return container


async def run_container_command(thread: Thread, container):
    exec_result = container.exec_run(
        cmd=["python", "-c", "print('Hello, World!')"], stdout=True, stderr=True
    )

    # Log the output
    await sync_to_async(Log.objects.create)(
        thread=thread,
        sender="system",
        type="output",
        payload=exec_result.output.decode("utf-8"),
    )

    # Update thread state
    thread.state = "completed"
    await sync_to_async(thread.save)()

    return exec_result.output.decode("utf-8")


async def start_thread_background(thread: Thread, docker_client):
    try:
        # Create or get container
        container = await create_container(thread.id, docker_client)

        # Update thread metadata
        thread.metadata.update(
            {
                "container_id": container.id,
                "image": "python:3.12",
                "network": "wandb_network",
            }
        )
        await sync_to_async(thread.save)()

        # Run the command
        await run_container_command(thread, container)

    except Exception as e:
        # Handle any errors in background task
        thread.state = "error"
        thread.metadata["error"] = str(e)
        await sync_to_async(thread.save)()
        await sync_to_async(Log.objects.create)(
            thread=thread,
            sender="system",
            type="error",
            payload=str(e),
        )


### API


@app.api.post("/settings/openai")
def update_openai_settings(request):
    try:
        data = json.loads(request.body)

        # Validate required fields
        required_fields = ["api_endpoint", "api_key"]
        if not all(field in data for field in required_fields):
            return {"error": "Missing required fields"}

        # Update or create settings
        Settings.objects.update_or_create(
            key="api_endpoint", defaults={"value": data["api_endpoint"]}
        )

        Settings.objects.update_or_create(
            key="api_key", defaults={"value": data["api_key"]}
        )

        # Handle optional api_model setting
        if "api_model" in data:
            Settings.objects.update_or_create(
                key="api_model", defaults={"value": data["api_model"]}
            )

        return {"message": "Settings updated successfully"}
    except json.JSONDecodeError:
        return {"error": "Invalid JSON payload"}
    except Exception as e:
        return {"error": "Failed to update settings"}


@app.api.get("/settings/openai/models")
def get_openai_models(request):
    try:
        # Get settings
        api_endpoint = Settings.objects.get(key="api_endpoint").value
        api_key = Settings.objects.get(key="api_key").value
    except Settings.DoesNotExist:
        return {"error": "OpenAI API endpoint and key must be configured first"}

    try:
        # Initialize OpenAI client
        client = OpenAI(base_url=api_endpoint, api_key=api_key)

        # Fetch models
        models = client.models.list()
        return {"models": [model.id for model in models]}

    except Exception as e:
        return {"error": f"Failed to fetch models from OpenAI API: {str(e)}"}


@app.api.post("/thread/create")
def create_thread(request):
    try:
        data = json.loads(request.body)

        # Validate required fields
        if "thread_name" not in data:
            return {"error": "thread_name is required"}

        # Create thread
        thread = Thread.objects.create(
            thread_name=data["thread_name"],
            metadata=data.get("metadata", {}),
        )

        return {
            "message": "Thread created successfully",
            "thread": {
                "id": thread.id,
                "thread_name": thread.thread_name,
                "state": thread.state,
                "created_on": thread.created_on,
            },
        }

    except Exception as e:
        return {"error": f"Failed to create thread: {str(e)}"}


@app.api.get("/threads")
def list_threads(request):
    try:
        threads = Thread.objects.all()
        thread_list = []

        for thread in threads:
            thread_data = {
                "id": thread.id,
                "thread_name": thread.thread_name,
                "state": thread.state,
                "created_on": thread.created_on,
                "log_count": thread.logs.count(),
                "metadata": thread.metadata,
            }
            thread_list.append(thread_data)

        return {"threads": thread_list}

    except Exception as e:
        return {"error": f"Failed to list threads: {str(e)}"}


@app.api.get("/thread/{thread_id}")
def get_thread(request, thread_id: str):
    try:
        # Get thread
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            return {"error": "Thread not found"}

        # Check container health if container exists
        container_healthy = False
        container_status = "not created"

        # Use thread ID to derive container name
        container_name = f"{thread_id}_wandb"
        docker_client = docker.from_env()
        try:
            container = docker_client.containers.get(container_name)
            container_status = container.status
            container_healthy = container_status == "running"
        except docker.errors.NotFound:
            container_status = "Not running"

        # Prepare response data
        thread_data = {
            "id": thread.id,
            "thread_name": thread.thread_name,
            "state": thread.state,
            "created_on": thread.created_on,
            "edited_on": thread.edited_on,
            "log_count": thread.logs.count(),
            "metadata": thread.metadata,
            "health": {"healthy": container_healthy, "status": container_status},
            "logs": [
                {
                    "id": log.id,
                    "sender": log.sender,
                    "type": log.type,
                    "payload": log.payload,
                    "created_on": log.created_on,
                }
                for log in thread.logs.all()
            ],
        }

        return thread_data

    except Exception as e:
        return {"error": f"Failed to get thread details: {str(e)}"}


@app.api.put("/thread/{thread_id}")
def update_thread(request, thread_id: str):
    try:
        data = json.loads(request.body)

        # Get thread
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            return {"error": "Thread not found"}

        # Update fields if provided
        if "thread_name" in data:
            thread.thread_name = data["thread_name"]

        if "metadata" in data:
            thread.metadata.update(data["metadata"])

        thread.save()

        return {
            "message": "Thread updated successfully",
            "thread": {
                "id": thread.id,
                "thread_name": thread.thread_name,
                "state": thread.state,
                "metadata": thread.metadata,
            },
        }

    except Exception as e:
        return {"error": f"Failed to update thread: {str(e)}"}


@app.api.post("/thread/{thread_id}/start")
async def start_thread(request, thread_id: str):
    try:
        # Get thread
        thread = await sync_to_async(Thread.objects.get)(id=thread_id)

        # Update thread state to starting
        thread.state = "starting"
        await sync_to_async(thread.save)()

        # Return immediate response
        response = {
            "message": "Thread starting",
            "thread_id": thread_id,
            "state": thread.state,
        }

        # Initialize Docker client
        docker_client = docker.from_env()

        # Start background tasks
        asyncio.create_task(start_thread_background(thread, docker_client))

        return response

    except Thread.DoesNotExist:
        return {"error": "Thread not found"}
    except Exception as e:
        return {"error": f"Thread operation failed: {str(e)}"}


@app.api.delete("/thread/{thread_id}")
def delete_thread(request, thread_id: str):
    try:
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            return {"error": "Thread not found"}

        # Delete associated container if it exists
        container_name = f"{thread_id}_wandb"
        docker_client = docker.from_env()
        try:
            container = docker_client.containers.get(container_name)
            container.remove(force=True)
        except docker.errors.NotFound:
            pass  # Container doesn't exist, continue with thread deletion

        thread.delete()
        return {"message": "Thread deleted successfully"}

    except Exception as e:
        return {"error": f"Failed to delete thread: {str(e)}"}


@app.api.post("/thread/{thread_id}/log/create")
def create_log(request, thread_id: str):
    try:
        data = json.loads(request.body)

        # Get thread
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            return {"error": "Thread not found"}

        # Validate required fields
        required_fields = ["sender", "type", "payload"]
        if not all(field in data for field in required_fields):
            return {"error": "Missing required fields: 'sender', 'type', or 'payload'."}

        # Create log
        log = Log.objects.create(
            thread=thread,
            sender=data["sender"],
            type=data["type"],
            payload=data["payload"],
            metadata=data.get("metadata", {}),
        )

        return {
            "message": "Log created successfully",
            "log": {
                "id": log.id,
                "sender": log.sender,
                "type": log.type,
                "payload": log.payload,
                "created_on": log.created_on,
                "metadata": log.metadata,
            },
        }

    except Exception as e:
        return {"error": f"Failed to create log: {str(e)}"}


@app.api.put("/log/{log_id}")
def update_log(request, log_id: str):
    try:
        data = json.loads(request.body)

        # Get log
        try:
            log = Log.objects.get(id=log_id)
        except Log.DoesNotExist:
            return {"error": "Log not found"}

        # Update fields if provided
        if "sender" in data:
            log.sender = data["sender"]
        if "type" in data:
            log.type = data["type"]
        if "payload" in data:
            log.payload = data["payload"]
        if "metadata" in data:
            log.metadata.update(data["metadata"])

        log.save()

        return {
            "message": "Log updated successfully",
            "log": {
                "id": log.id,
                "sender": log.sender,
                "type": log.type,
                "payload": log.payload,
                "created_on": log.created_on,
                "edited_on": log.edited_on,
                "metadata": log.metadata,
            },
        }

    except Exception as e:
        return {"error": f"Failed to update log: {str(e)}"}


@app.api.delete("/log/{log_id}")
def delete_log(request, log_id: str):
    try:
        try:
            log = Log.objects.get(id=log_id)
        except Log.DoesNotExist:
            return {"error": "Log not found"}

        log.delete()
        return {"message": "Log deleted successfully"}

    except Exception as e:
        return {"error": f"Failed to delete log: {str(e)}"}


### Routes


@app.route("/")
def index(request):
    return render(request, "index.html")
