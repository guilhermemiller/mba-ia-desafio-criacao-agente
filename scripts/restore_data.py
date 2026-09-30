import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import restore_initial_data

if __name__ == "__main__":
    restore_initial_data()
    print("Dados iniciais restaurados com sucesso!")
