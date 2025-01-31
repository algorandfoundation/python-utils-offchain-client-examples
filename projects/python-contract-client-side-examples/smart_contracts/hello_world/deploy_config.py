import logging

from algokit_utils import (
    AlgorandClient,
    AppClientCompilationParams,
    OnSchemaBreak,
    OnUpdate,
    SigningAccount,
    ApplicationSpecification,
)

logger = logging.getLogger(__name__)


# define deployment behaviour based on supplied app spec
def deploy(
    app_spec: ApplicationSpecification,
    deployer: SigningAccount,
) -> None:
    from smart_contracts.artifacts.hello_world.hello_world_client import (
        HelloWorldFactory,
    )

    algorand = AlgorandClient.default_localnet()

    app_factory = algorand.client.get_typed_app_factory(
        typed_factory=HelloWorldFactory,
        app_name="hello-world",
        default_sender=deployer.address,
        default_signer=deployer.signer,
        version="1.0",
        compilation_params=AppClientCompilationParams(
            updatable=True,
            deletable=False,
        ),
    )

    app_client, deploy_result = app_factory.deploy(
        on_update=OnUpdate.UpdateApp,
        on_schema_break=OnSchemaBreak.Fail,
    )
    print(deploy_result.app.app_id)

    name = "world"

    response = app_client.send.hello(args=("Hello",))
    logger.info(
        f"Called hello on {app_spec.contract.name} ({app_client.app_id}) "
        f"with name={name}, received: {response.abi_return}"
    )
