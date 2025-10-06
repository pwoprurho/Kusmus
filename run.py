from kusmusapp import create_app, socketio

app = create_app()

if __name__ == '__main__':
    # Use socketio.run() to enable real-time features
    socketio.run(app, debug=True)