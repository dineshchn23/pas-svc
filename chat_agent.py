from datetime import datetime

# Chat feature removed.
# These placeholder files remain for history and to avoid import errors in other branches.
# If you want these files deleted entirely, remove them from the repository in a follow-up commit.

def info():
    return {
        'removed': True,
        'removed_at': datetime.utcnow().isoformat() + 'Z',
        'note': 'Chat functionality has been removed from this project. See commit history for details.'
    }
