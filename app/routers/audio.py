from fastapi import APIRouter
from fastapi.websockets import WebSocket
from app.database.database import database
from datetime import datetime
from app.services.deepgram import DeepgramClient
from app.services.connection import manager
from app.models.requests import TranscribeAudioRequest
from app.services.anthropic import generate_note_stream, ask_claude

router = APIRouter()
db = database()

async def handle_start_recording(websocket: WebSocket, user_id: str, data: dict, deepgram: DeepgramClient):
    visit = db.update_visit(visit_id=data["visit_id"], status="RECORDING", recording_started_at=datetime.utcnow())
    try:
        async def handle_transcription(result, loop=None):
            print("Result", result)
            if "transcript" in result and result.get("is_final", False):
                current_transcript = db.get_visit(visit["visit_id"])["transcript"]
                timestamp = datetime.fromisoformat(result["timestamp"]).strftime("%H:%M:%S")
                if current_transcript:
                    new_transcript = current_transcript + "\n[" + timestamp + "] " + result["transcript"]
                else:
                    new_transcript = "[" + timestamp + "] " + result["transcript"]
                db.update_visit(visit["visit_id"], transcript=new_transcript)
        await deepgram.setup_connection(handle_transcription, visit["visit_id"])
        await manager.broadcast_to_all(websocket, user_id, {
            "type": "start_recording",
            "data": {
                "visit_id": visit["visit_id"],
                "status": visit["status"],
                "recording_started_at": visit["recording_started_at"],
            }
        })  
    except Exception as e:
        print(e)
        await manager.broadcast_to_user(websocket, user_id, {
            "type": "error",
            "data": {"message": str(e)}
        })
        return

async def handle_pause_recording(websocket: WebSocket, user_id: str, data: dict, deepgram: DeepgramClient):
    visit = db.update_visit(visit_id=data["visit_id"], status="PAUSED")
    try:
        await deepgram.close_connection()
        await manager.broadcast_to_all(websocket, user_id, {
            "type": "pause_recording",
            "data": {
                "visit_id": visit["visit_id"],
                "status": visit["status"],
            }
        })
    except Exception as e:
        print(e)
        await manager.broadcast_to_user(websocket, user_id, {
            "type": "error",
            "data": {"message": str(e)}
        })
        return

async def handle_resume_recording(websocket: WebSocket, user_id: str, data: dict, deepgram: DeepgramClient):
    visit = db.update_visit(visit_id=data["visit_id"], status="RECORDING")
    try:
        async def handle_transcription(result, loop=None):
            print("Result", result)
            if "transcript" in result and result.get("is_final", False):
                current_transcript = db.get_visit(visit["visit_id"])["transcript"]
                timestamp = datetime.fromisoformat(result["timestamp"]).strftime("%H:%M:%S")
                if current_transcript:
                    new_transcript = current_transcript + "\n[" + timestamp + "] " + result["transcript"]
                else:
                    new_transcript = "[" + timestamp + "] " + result["transcript"]
                db.update_visit(visit["visit_id"], transcript=new_transcript)

        await deepgram.setup_connection(handle_transcription, visit["visit_id"])
        await manager.broadcast_to_all(websocket, user_id, {
            "type": "resume_recording",
            "data": {
                "visit_id": visit["visit_id"],
                "status": visit["status"],
            }
        })
    except Exception as e:
        print(e)
        await manager.broadcast_to_user(websocket, user_id, {
            "type": "error",
            "data": {"message": str(e)}
        })
        return

async def handle_finish_recording(websocket: WebSocket, user_id: str, data: dict, deepgram: DeepgramClient):
    visit = db.update_visit(visit_id=data["visit_id"], status="GENERATING_NOTE", recording_finished_at=datetime.utcnow())

    try:
        await deepgram.close_connection()
        name = visit["name"]
        if name == "New Visit" or name == "":
            name = await ask_claude(f"What is the patient's name? The visit transcript and additional context is: {visit['transcript']} {visit['additional_context']} Just return the name, nothing else, no comments, no nothing. Correct output: John Doe. Wrong output: The patient's name is John Doe. Make sure the output is only the name, nothing else.")
            visit = db.update_visit(visit["visit_id"], name=name)
        visit = db.update_visit(visit["visit_id"], template_modified_at=datetime.utcnow())
        user = db.get_user(user_id)
        await manager.broadcast_to_all(websocket, user_id, {
            "type": "finish_recording",
            "data": {
                "visit_id": visit["visit_id"],
                "status": visit["status"],
                "recording_finished_at": visit["recording_finished_at"],
                "recording_duration": visit["recording_duration"],
                "transcript": visit["transcript"],
                "name": name,
                "template_modified_at": visit["template_modified_at"]
            }
        })

        note, note_generated_at = await generate_note_stream(
            template=db.get_template(visit["template_id"])['instructions'], 
            transcript=visit["transcript"], 
            additional_context=visit["additional_context"],
            user_specialty=user["user_specialty"],
            websocket=websocket,
            user_id=user_id,
            visit_id=visit["visit_id"]
        )

        visit = db.update_visit(visit["visit_id"], note=note, status="FINISHED", template_modified_at=note_generated_at)
    except Exception as e:
        print(e)
        await manager.broadcast_to_user(websocket, user_id, {
            "type": "error",
            "data": {"message": str(e)}
        })
        return
    
async def handle_audio_chunk(websocket: WebSocket, user_id: str, data: dict, deepgram: DeepgramClient):
    if "audio" in data:
        import base64
        try:
            audio_bytes = base64.b64decode(data["audio"])
            await deepgram.process_audio_chunk(audio_bytes)
        except Exception as e:
            await manager.broadcast_to_user(websocket, user_id, {
                "type": "error",
                "data": {"message": str(e)}
            })
            return
    else:
        await manager.broadcast_to_user(websocket, user_id, {
            "type": "error",
            "data": {"message": "Missing audio data in audio_chunk message"}
        })
        return


@router.post("/process_audio_buffer")
async def process_audio_buffer(request: TranscribeAudioRequest):
    deepgram = DeepgramClient()
    await deepgram.process_audio_buffer(request.audio_buffer)

