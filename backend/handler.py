import sys
import os

# Asegura que el directorio actual esté en el path para importaciones
sys.path.append(os.path.dirname(__file__))

from mangum import Mangum
from main import app

handler = Mangum(app)
