import logging

# This is the class you derive to create a plugin
from airflow.plugins_manager import AirflowPlugin

# Importing base classes that we need to derive
from airflow.models.baseoperator import BaseOperator
from airflow.utils.decorators import apply_defaults

logger = logging.getLogger('airflow.my_first_operator')

# Will show up under airflow.operators.my_first_plugin.MyFirstOperator
class MyFirstOperator(BaseOperator):

    @apply_defaults
    def __init__(
            self,
            name: str,
            my_operator_param,
            *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.name = name
        self.my_operator_param = my_operator_param

    def execute(self, context):
        logger.info('Hello World!')
        logger.info('operator_param: %s', self.operator_param)

# Defining the plugin class
class MyFirstPlugin(AirflowPlugin):
    name = 'my_first_plugin'
    operators = [MyFirstOperator]
