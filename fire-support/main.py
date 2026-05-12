from flask import Flask, request, jsonify
import logging
from logging_config import setup_logging
import sys

from support_service import SupportService
from llm.config import LLMConfig
from llm.llm_client import LLMClient
from llm.message_store_adapter import MessageStoreAdapter
from llm.agent_communication import AgentCommunication

app = Flask(__name__)

support_service: SupportService = None
llm_config: LLMConfig = None

@app.route('/start', methods=['POST'])
def start():
    """Start the support service with optional configuration"""
    global support_service, llm_config
    data = request.get_json() or {}
    
    llm_config_data = data.get('llm_config', {})
    llm_config = LLMConfig.from_dict(llm_config_data) if llm_config_data else LLMConfig()

    support_service = SupportService(llm_config=llm_config) if not support_service else support_service
    support_service._llm_config = llm_config

    support_service.start(config=data.get('config'))
    config_info = llm_config.to_dict()
    config_info.pop('llm_api_key', None) 
    
    return jsonify({
        "status": "started",
        "message": "Support service started",
        "llm_config": config_info
    })

@app.route('/stop', methods=['POST'])
def stop():
    """Stop the support service"""
    global support_service
    
    if support_service:
        support_service.stop()
        support_service = None
        return jsonify({"status": "stopped", "message": "Support service stopped"})
    else:
        return jsonify({"status": "error", "message": "Support service not running"}), 400

@app.route('/snapshot', methods=['GET'])
def snapshot():
    """Get current state snapshot"""
    global support_service
    
    if support_service:
        state = support_service.get_state_snapshot()
        return jsonify(state)
    else:
        return jsonify({"status": "error", "message": "Support service not running"}), 400

@app.route('/state', methods=['POST'])
def post_state():
    """POST current state (sectors + fireBrigades + optional config)"""
    global support_service
    if support_service is None:
        support_service = SupportService()
        support_service.start()
    payload = request.get_json() or {}
    support_service.update_state(payload)
    return jsonify({"status": "ok", "message": "State updated"})

@app.route('/analyze', methods=['POST'])
def analyze():
    """Trigger immediate analysis and return recommendations"""
    global support_service
    if support_service is None:
        return jsonify({"status": "error", "message": "Support service not running"}), 400
    recs = support_service.analyze_now()
    return jsonify({"status": "ok", "recommendations": recs})

@app.route('/recommendations', methods=['GET'])
def recommendations():
    """Get last generated recommendations"""
    global support_service
    if support_service is None:
        return jsonify({"status": "error", "message": "Support service not running"}), 400
    recs = support_service.get_last_recommendations()
    return jsonify({"status": "ok", "recommendations": recs})

@app.route('/config', methods=['GET'])
def get_config():
    """Get current LLM configuration"""
    global support_service, llm_config
    current_config = llm_config if llm_config else LLMConfig()
    config_dict = current_config.to_dict()
    config_dict.pop('llm_api_key', None)  # Don't expose API key
    return jsonify({
        "status": "ok",
        "config": config_dict
    })

@app.route('/config', methods=['POST'])
def update_config():
    """Update LLM configuration"""
    global support_service, llm_config
    
    data = request.get_json() or {}
    new_config = LLMConfig.from_dict(data)
    llm_config = new_config
    
    if support_service:
        support_service._llm_config = new_config
        use_llm = new_config.use_llm_coordination
        if use_llm and not support_service._llm_client:
        
            support_service._llm_client = LLMClient(
                model    = new_config.llm_model,
                api_key  = new_config.llm_api_key,
                base_url = new_config.llm_base_url
            )
            support_service._message_store_adapter = MessageStoreAdapter(support_service.rabbitmq)
            support_service._agent_communication = AgentCommunication(support_service._message_store_adapter)
    
    config_dict = new_config.to_dict()
    config_dict.pop('llm_api_key', None)
    
    return jsonify({
        "status": "ok",
        "message": "Configuration updated",
        "config": config_dict
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    setup_logging("fire-support")
    logger = logging.getLogger(__name__)
    logger.info("Fire Support Service Flask app starting...")
    logger.info("Support service will be started via POST /start endpoint")
    app.run(debug=False, host='0.0.0.0', port=5001)