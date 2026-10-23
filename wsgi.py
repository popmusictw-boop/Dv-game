import logging, os
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
import app as _appmod
app = getattr(_appmod, 'app', None) or _appmod.create_app()
