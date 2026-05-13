import asyncio
import logging
import sys
import threading
from flask import Flask, request, jsonify

from src.settings.communucation_settings import get_communication_settings
from src.settings.simulation_settings import get_simulation_settings
from src.engine.simple_simulation_engine import SimpleSimulationEngine
from src.engine.runner import EngineRunner
from src.logger.logging_config import setup_logging

logger = logging.getLogger(__name__)

app = Flask(__name__)

communication_settings = get_communication_settings()
simulation_settings = get_simulation_settings()

engine = SimpleSimulationEngine(simulation_settings, communication_settings)
runner = EngineRunner(engine, settings=communication_settings, simulation_settings=simulation_settings)
_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None

def _get_event_loop() -> asyncio.AbstractEventLoop:
    global _loop, _loop_thread
    if _loop is None or not _loop.is_running():
        _loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
        _loop_thread.start()
    return _loop

def _run_async(coro):
    loop = _get_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=30)

@app.route('/run_simulation', methods=['POST'])
def run():
    '''Start the simulation with the provided configuration.'''
    data = request.get_json()
    print("Received data:", data)

    if runner.engine.is_running():
        return jsonify({"status": "error", "message": "Simulation already running"}), 400

    try:
        _run_async(runner.start(data))
        return jsonify({"status": "ok", "message": "Simulation started"})
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback_str = traceback.format_exc()
        logger.error(f"Error starting simulation: {error_msg}\n{traceback_str}")
        return jsonify({"status": "error", "message": error_msg}), 500


@app.route('/stop_simulation', methods=['POST'])
def stop():
    """Stop the simulation. Idempotent - succeeds even if already stopped."""
    was_running = runner.engine.is_running()
    
    if not was_running:
        logger.info("Stop requested but simulation was already stopped")
        return jsonify({"status": "ok", "message": "Simulation was already stopped"})

    try:
        _run_async(runner.stop())
        return jsonify({"status": "ok", "message": "Simulation stopped"})
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback_str = traceback.format_exc()
        logger.error(f"Error stopping simulation: {error_msg}\n{traceback_str}")
        return jsonify({"status": "error", "message": error_msg}), 500


@app.route('/step', methods=['POST'])
def step():
    data = request.get_json() or {}
    ticks = data.get("ticks", 1)

    if not runner.engine.is_running():
        return jsonify({"status": "error", "message": "Simulation not running"}), 400

    try:
        result = _run_async(runner.manual_step(ticks))
        return jsonify({
            "status": "ok",
            "ticks": ticks,
            "sectors_on_fire": len(result.get("sector_states", [])),
            "sensor_messages_count": sum(len(v) for v in result.get("sensor_messages", {}).values())
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/snapshot', methods=['GET'])
def snapshot():
    """Pobierz aktualny stan symulacji."""
    try:
        snap = runner.snapshot()
        return jsonify({"status": "ok", "snapshot": snap})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check."""
    return jsonify({
        "status": "ok",
        "running": runner.engine.is_running()
    })


@app.route('/set_speed', methods=['POST'])
def set_speed():
    """
    Update simulation speed at runtime.
    Payload format:{ "tickInterval": 1.0  # seconds between simulation ticks }
    """
    data = request.get_json() or {}
    tick_interval = data.get("tickInterval")

    if tick_interval is None:
        return jsonify({"status": "error", "message": "tickInterval is required"}), 400
    
    try:
        value = float(tick_interval)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "tickInterval must be a number"}), 400

    if value <= 0:
        return jsonify({"status": "error", "message": "tickInterval must be > 0"}), 400

    runner.set_tick_interval(value)
    return jsonify({"status": "ok", "tickInterval": value})

@app.route('/orderFireBrigade', methods=['POST'])
def order_fire_brigade():
    """Receive fire brigade order from backend and forward to agent manager via RabbitMQ."""
    try:
        data = request.get_json()
        logger.info(f"[HTTP] /orderFireBrigade from {request.remote_addr} payload: {data}")
        
        if not runner.engine.is_running():
            return jsonify({"status": "error", "message": "Simulation not running"}), 400
        
        # Add order to message store for agent manager to process
        # Use queue name (with underscores) to match how RabbitMQ consumers store messages
        from src.messaging.topics import TopicRegistry
        queue_name = TopicRegistry.FIRE_BRIGADE_ACTIONS.value.replace('.', '_')
        runner.store.add_received_message(data, queue_name)
        
        return jsonify({"status": "ok", "message": "Order received"})
    except Exception as e:
        logger.error(f"Error processing fire brigade order: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/orderForestPatrol', methods=['POST'])
def order_forest_patrol():
    """Receive forester patrol order from backend and forward to agent manager via RabbitMQ."""
    try:
        data = request.get_json()
        logger.info(f"[HTTP] /orderForestPatrol from {request.remote_addr} payload: {data}")
        
        if not runner.engine.is_running():
            return jsonify({"status": "error", "message": "Simulation not running"}), 400
        
        # Add order to message store for agent manager to process
        # Use queue name (with underscores) to match how RabbitMQ consumers store messages
        from src.messaging.topics import TopicRegistry
        queue_name = TopicRegistry.FORESTER_ACTIONS.value.replace('.', '_')
        runner.store.add_received_message(data, queue_name)
        
        return jsonify({"status": "ok", "message": "Order received"})
    except Exception as e:
        logger.error(f"Error processing forester patrol order: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    setup_logging("fire-simulation")

    print("Starting Fire Simulation API...")
    print("Endpoints:")
    print("  POST /run_simulation  - start simulation with config")
    print("  POST /stop_simulation - stop simulation")
    print("  POST /step            - manual step (body: {ticks: n})")
    print("  POST /orderFireBrigade - send fire brigade order")
    print("  POST /orderForestPatrol - send forester patrol order")
    print("  GET  /snapshot        - get current state")
    print("  GET  /health          - health check")
    print("  POST /set_speed       - update simulation tick interval")

    app.run(debug=False, host='0.0.0.0', port=5000)
