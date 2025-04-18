from flask import Flask, request, jsonify, render_template
from twilio.rest import Client
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import json
import atexit
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Get environment variables or use defaults for local testing
twilio_account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
twilio_auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
twilio_whatsapp_number = os.environ.get('TWILIO_WHATSAPP_NUMBER')

# Initialize Twilio client if credentials are available
client = None
if twilio_account_sid and twilio_auth_token:
    try:
        client = Client(twilio_account_sid, twilio_auth_token)
        logger.info("Twilio client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Twilio client: {str(e)}")

# Data storage - we'll use in-memory storage with JSON backup for persistence
DATA_FILE = 'data/cleaning_rota.json'

# Create data directory if it doesn't exist
os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)

# Data structure
data = {
    "members": [],
    "tasks": [],
    "assignments": []
}

# Load data from file if exists
def load_data():
    global data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                logger.info("Data loaded successfully")
        else:
            # If no file exists, create default data
            data = {
                "members": [],
                "tasks": [
                    {
                        "id": str(uuid.uuid4()),
                        "name": "Kitchen cleaning",
                        "description": "Clean kitchen surfaces and floor",
                        "frequency": "weekly"
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "name": "Bathroom cleaning",
                        "description": "Clean bathroom, including shower, toilet and sink",
                        "frequency": "weekly"
                    }
                ],
                "assignments": []
            }
            save_data()
            logger.info("Default data created")
    except Exception as e:
        logger.error(f"Error loading data: {str(e)}")
        # If there's an error, initialize with empty data
        data = {"members": [], "tasks": [], "assignments": []}

# Save data to file
def save_data():
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
            logger.info("Data saved successfully")
    except Exception as e:
        logger.error(f"Error saving data: {str(e)}")

# Load data at startup
load_data()

# HTML Templates
@app.route('/')
def home_page():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cleaning Rota System</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 20px; line-height: 1.6; }
            h1 { color: #333; }
            .container { max-width: 800px; margin: 0 auto; }
            .endpoints { background: #f4f4f4; padding: 20px; border-radius: 5px; }
            pre { background: #e4e4e4; padding: 10px; border-radius: 3px; overflow-x: auto; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>WhatsApp Cleaning Rota API</h1>
            <p>Welcome to the WhatsApp Cleaning Rota System. Use the following endpoints to manage your cleaning rota:</p>
            
            <div class="endpoints">
                <h2>Available Endpoints:</h2>
                <ul>
                    <li><b>GET /api/members</b> - List all members</li>
                    <li><b>POST /api/members</b> - Add a new member</li>
                    <li><b>DELETE /api/members/{member_id}</b> - Remove a member</li>
                    <li><b>GET /api/tasks</b> - List all tasks</li>
                    <li><b>POST /api/tasks</b> - Add a new task</li>
                    <li><b>DELETE /api/tasks/{task_id}</b> - Remove a task</li>
                    <li><b>GET /api/assignments</b> - List all assignments</li>
                    <li><b>POST /api/assign</b> - Create a new assignment</li>
                    <li><b>POST /api/notify</b> - Send notifications to all members with current tasks</li>
                    <li><b>POST /api/notify/{member_id}</b> - Send notification to a specific member</li>
                </ul>
            </div>
            
            <h2>Example: Adding a new member</h2>
            <pre>
POST /api/members
{
    "name": "John Doe",
    "phone": "+1234567890" 
}
            </pre>
            
            <h2>WhatsApp Commands</h2>
            <p>Users can send the following commands to the Twilio WhatsApp number:</p>
            <ul>
                <li><b>tasks</b> - Get a list of your current tasks</li>
                <li><b>done [task name]</b> - Mark a task as complete</li>
                <li><b>help</b> - Get a list of available commands</li>
            </ul>
        </div>
    </body>
    </html>
    """

# API Endpoints

# Members endpoints
@app.route('/api/members', methods=['GET'])
def get_members():
    return jsonify(data["members"])

@app.route('/api/members', methods=['POST'])
def add_member():
    try:
        new_member = request.json
        
        # Validate required fields
        if not new_member or 'name' not in new_member or 'phone' not in new_member:
            return jsonify({"error": "Name and phone number required"}), 400
        
        # Validate phone number format
        phone = new_member['phone']
        if not phone.startswith('+'):
            return jsonify({"error": "Phone number must be in international format (starting with +)"}), 400
        
        # Create member with UUID
        member_id = str(uuid.uuid4())
        member = {
            "id": member_id,
            "name": new_member["name"],
            "phone": new_member["phone"],
            "date_added": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        data["members"].append(member)
        save_data()
        
        return jsonify({"status": "success", "member": member}), 201
    except Exception as e:
        logger.error(f"Error adding member: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/members/<member_id>', methods=['DELETE'])
def delete_member(member_id):
    try:
        # Find the member
        for i, member in enumerate(data["members"]):
            if member["id"] == member_id:
                # Remove member
                removed_member = data["members"].pop(i)
                
                # Remove any assignments for this member
                data["assignments"] = [a for a in data["assignments"] 
                                      if a["member_id"] != member_id]
                
                save_data()
                return jsonify({"status": "success", "removed": removed_member})
        
        return jsonify({"error": "Member not found"}), 404
    except Exception as e:
        logger.error(f"Error deleting member: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Tasks endpoints
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    return jsonify(data["tasks"])

@app.route('/api/tasks', methods=['POST'])
def add_task():
    try:
        new_task = request.json
        
        # Validate required fields
        if not new_task or 'name' not in new_task:
            return jsonify({"error": "Task name required"}), 400
        
        # Set defaults for optional fields
        description = new_task.get("description", "")
        frequency = new_task.get("frequency", "weekly")
        
        # Validate frequency
        valid_frequencies = ["daily", "weekly", "biweekly", "monthly"]
        if frequency not in valid_frequencies:
            return jsonify({"error": f"Frequency must be one of: {', '.join(valid_frequencies)}"}), 400
        
        # Create task with UUID
        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "name": new_task["name"],
            "description": description,
            "frequency": frequency,
            "date_added": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        data["tasks"].append(task)
        save_data()
        
        return jsonify({"status": "success", "task": task}), 201
    except Exception as e:
        logger.error(f"Error adding task: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    try:
        # Find the task
        for i, task in enumerate(data["tasks"]):
            if task["id"] == task_id:
                # Remove task
                removed_task = data["tasks"].pop(i)
                
                # Remove any assignments for this task
                data["assignments"] = [a for a in data["assignments"] 
                                      if a["task_id"] != task_id]
                
                save_data()
                return jsonify({"status": "success", "removed": removed_task})
        
        return jsonify({"error": "Task not found"}), 404
    except Exception as e:
        logger.error(f"Error deleting task: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Assignments endpoints
@app.route('/api/assignments', methods=['GET'])
def get_assignments():
    # Add member and task details to assignments for easier consumption
    enriched_assignments = []
    for assignment in data["assignments"]:
        enriched = assignment.copy()
        
        # Find member details
        for member in data["members"]:
            if member["id"] == assignment["member_id"]:
                enriched["member_name"] = member["name"]
                enriched["member_phone"] = member["phone"]
                break
        
        # Find task details
        for task in data["tasks"]:
            if task["id"] == assignment["task_id"]:
                enriched["task_name"] = task["name"]
                enriched["task_description"] = task["description"]
                enriched["task_frequency"] = task["frequency"]
                break
        
        enriched_assignments.append(enriched)
    
    return jsonify(enriched_assignments)

@app.route('/api/assign', methods=['POST'])
def create_assignment():
    try:
        assignment_data = request.json
        
        # Validate required fields
        if not assignment_data or 'member_id' not in assignment_data or 'task_id' not in assignment_data:
            return jsonify({"error": "Member ID and Task ID required"}), 400
        
        # Verify member exists
        member_exists = False
        for member in data["members"]:
            if member["id"] == assignment_data["member_id"]:
                member_exists = True
                member_name = member["name"]
                break
                
        if not member_exists:
            return jsonify({"error": "Member not found"}), 404
        
        # Verify task exists
        task_exists = False
        for task in data["tasks"]:
            if task["id"] == assignment_data["task_id"]:
                task_exists = True
                task_name = task["name"]
                break
                
        if not task_exists:
            return jsonify({"error": "Task not found"}), 404
        
        # Check if this assignment already exists
        for assignment in data["assignments"]:
            if (assignment["member_id"] == assignment_data["member_id"] and 
                assignment["task_id"] == assignment_data["task_id"]):
                return jsonify({"error": "This assignment already exists"}), 409
        
        # Create assignment
        assignment_id = str(uuid.uuid4())
        due_date = assignment_data.get("due_date", (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"))
        
        assignment = {
            "id": assignment_id,
            "member_id": assignment_data["member_id"],
            "task_id": assignment_data["task_id"],
            "assigned_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "due_date": due_date,
            "completed": False,
            "completion_date": None
        }
        
        data["assignments"].append(assignment)
        save_data()
        
        # Return success with added member and task names for convenience
        return jsonify({
            "status": "success", 
            "assignment": assignment,
            "member_name": member_name,
            "task_name": task_name
        }), 201
    except Exception as e:
        logger.error(f"Error creating assignment: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/assignments/<assignment_id>/complete', methods=['POST'])
def complete_assignment(assignment_id):
    try:
        # Find the assignment
        for assignment in data["assignments"]:
            if assignment["id"] == assignment_id:
                assignment["completed"] = True
                assignment["completion_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_data()
                return jsonify({"status": "success", "assignment": assignment})
        
        return jsonify({"error": "Assignment not found"}), 404
    except Exception as e:
        logger.error(f"Error completing assignment: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Notification endpoints
@app.route('/api/notify', methods=['POST'])
def notify_all():
    if not client:
        return jsonify({"error": "Twilio client not configured"}), 500
    
    try:
        notifications_sent = []
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # For each active assignment, send a notification
        for assignment in data["assignments"]:
            if not assignment["completed"]:
                # Get member details
                member = next((m for m in data["members"] if m["id"] == assignment["member_id"]), None)
                if not member:
                    continue
                    
                # Get task details
                task = next((t for t in data["tasks"] if t["id"] == assignment["task_id"]), None)
                if not task:
                    continue
                
                # Create message
                message_body = f"Hi {member['name']}! This is a reminder about your cleaning task: {task['name']}"
                if task["description"]:
                    message_body += f"\nDetails: {task['description']}"
                message_body += f"\nDue date: {assignment['due_date']}"
                
                try:
                    # Send WhatsApp message
                    message = client.messages.create(
                        body=message_body,
                        from_=f"whatsapp:{twilio_whatsapp_number}",
                        to=f"whatsapp:{member['phone']}"
                    )
                    
                    notifications_sent.append({
                        "member": member["name"],
                        "task": task["name"],
                        "message_sid": message.sid
                    })
                except Exception as e:
                    logger.error(f"Error sending notification to {member['name']}: {str(e)}")
        
        return jsonify({"status": "success", "notifications_sent": notifications_sent})
    except Exception as e:
        logger.error(f"Error sending notifications: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/notify/<member_id>', methods=['POST'])
def notify_member(member_id):
    if not client:
        return jsonify({"error": "Twilio client not configured"}), 500
    
    try:
        # Find the member
        member = next((m for m in data["members"] if m["id"] == member_id), None)
        if not member:
            return jsonify({"error": "Member not found"}), 404
            
        # Get the member's active assignments
        active_assignments = [a for a in data["assignments"] 
                             if a["member_id"] == member_id and not a["completed"]]
        
        if not active_assignments:
            return jsonify({"status": "success", "message": "No active assignments found for this member"})
        
        # Compile tasks into a single message
        tasks_text = ""
        for idx, assignment in enumerate(active_assignments, 1):
            # Get task details
            task = next((t for t in data["tasks"] if t["id"] == assignment["task_id"]), None)
            if task:
                tasks_text += f"{idx}. {task['name']} - Due: {assignment['due_date']}\n"
                if task["description"]:
                    tasks_text += f"   {task['description']}\n"
        
        message_body = f"Hi {member['name']}! Here are your cleaning tasks:\n\n{tasks_text}"
        message_body += "\nReply with 'done [task name]' when you complete a task."
        
        # Send WhatsApp message
        message = client.messages.create(
            body=message_body,
            from_=f"whatsapp:{twilio_whatsapp_number}",
            to=f"whatsapp:{member['phone']}"
        )
        
        return jsonify({
            "status": "success", 
            "message_sid": message.sid,
            "member": member["name"],
            "tasks_count": len(active_assignments)
        })
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Webhook for WhatsApp incoming messages
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Get incoming message details
        incoming_msg = request.values.get('Body', '').strip()
        sender = request.values.get('From', '')
        
        # Strip the "whatsapp:" prefix from the sender
        if sender.startswith("whatsapp:"):
            sender = sender[9:]
        
        logger.info(f"Received message from {sender}: {incoming_msg}")
        
        # Find the member by phone number
        member = next((m for m in data["members"] if m["phone"] == sender), None)
        
        if not member:
            response = "Sorry, your number is not registered in our system. Please contact the administrator."
            return create_twilio_response(response)
        
        # Process commands
        incoming_msg = incoming_msg.lower()
        
        if incoming_msg == 'tasks':
            # List the member's tasks
            active_assignments = [a for a in data["assignments"] 
                                if a["member_id"] == member["id"] and not a["completed"]]
            
            if not active_assignments:
                response = f"Hi {member['name']}! You don't have any active cleaning tasks."
            else:
                tasks_text = ""
                for idx, assignment in enumerate(active_assignments, 1):
                    task = next((t for t in data["tasks"] if t["id"] == assignment["task_id"]), None)
                    if task:
                        tasks_text += f"{idx}. {task['name']} - Due: {assignment['due_date']}\n"
                
                response = f"Hi {member['name']}! Here are your cleaning tasks:\n\n{tasks_text}"
        
        elif incoming_msg.startswith('done '):
            # Mark a task as complete
            task_name = incoming_msg[5:].strip().lower()
            
            completed = False
            for assignment in data["assignments"]:
                if assignment["member_id"] == member["id"] and not assignment["completed"]:
                    task = next((t for t in data["tasks"] if t["id"] == assignment["task_id"]), None)
                    if task and task["name"].lower() == task_name:
                        assignment["completed"] = True
                        assignment["completion_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        completed = True
                        save_data()
                        break
            
            if completed:
                response = f"Great job {member['name']}! The task '{task_name}' has been marked as complete."
            else:
                response = f"Sorry {member['name']}, I couldn't find an active task named '{task_name}' assigned to you."
        
        elif incoming_msg == 'help':
            response = f"Hi {member['name']}! Here are the available commands:\n\n• tasks - Get a list of your current tasks\n• done [task name] - Mark a task as complete\n• help - Show this help message"
        
        else:
            response = f"Hi {member['name']}! I didn't understand that command. Send 'help' to see available commands."
        
        return create_twilio_response(response)
    
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return create_twilio_response("Sorry, there was an error processing your request.")

def create_twilio_response(message):
    return f"""
    <?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Message>{message}</Message>
    </Response>
    """

# Scheduled tasks

# Function to check due tasks and send reminders
def check_due_tasks():
    if not client:
        logger.warning("Twilio client not configured, skipping due task check")
        return
    
    try:
        logger.info("Checking for due tasks...")
        current_date = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # For each assignment due today or tomorrow, send a reminder
        for assignment in data["assignments"]:
            if not assignment["completed"] and (assignment["due_date"] == current_date or assignment["due_date"] == tomorrow):
                # Get member details
                member = next((m for m in data["members"] if m["id"] == assignment["member_id"]), None)
                if not member:
                    continue
                    
                # Get task details
                task = next((t for t in data["tasks"] if t["id"] == assignment["task_id"]), None)
                if not task:
                    continue
                
                # Determine urgency of message
                if assignment["due_date"] == current_date:
                    urgency = "due today"
                else:
                    urgency = "due tomorrow"
                
                # Create message
                message_body = f"Hi {member['name']}! Reminder: Your cleaning task '{task['name']}' is {urgency}."
                if task["description"]:
                    message_body += f"\nDetails: {task['description']}"
                
                try:
                    # Send WhatsApp message
                    client.messages.create(
                        body=message_body,
                        from_=f"whatsapp:{twilio_whatsapp_number}",
                        to=f"whatsapp:{member['phone']}"
                    )
                    
                    logger.info(f"Sent reminder to {member['name']} for task {task['name']}")
                except Exception as e:
                    logger.error(f"Error sending reminder to {member['name']}: {str(e)}")
        
    except Exception as e:
        logger.error(f"Error in scheduled task check: {str(e)}")

# Set up scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_due_tasks, trigger="interval", hours=24, start_date='2023-01-01 08:00:00')
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())

# Health check endpoint for monitoring
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "twilio_configured": client is not None,
        "members_count": len(data["members"]),
        "tasks_count": len(data["tasks"]),
        "assignments_count": len(data["assignments"])
    })

# Run the application
if __name__ == '__main__':
    # Use the PORT environment variable provided by Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
