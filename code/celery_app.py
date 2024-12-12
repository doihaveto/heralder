import sys
import logging
import settings
from celery import Celery, Task
from celery.signals import after_setup_logger

def celery_init_app(app):
    class FlaskTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(settings)
    celery_app.set_default()
    app.extensions['celery'] = celery_app
    return celery_app

@after_setup_logger.connect()
def config_loggers(logger, *args, **kwags):
    my_handler = logging.StreamHandler(sys.stdout)
    my_handler.setLevel(logging.INFO) 
    my_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    my_handler.setFormatter(my_formatter)
    logger.addHandler(my_handler)
