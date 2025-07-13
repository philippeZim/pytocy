import click
from pathlib import Path
from py2cy.config import AppConfig
from py2cy.orchestrator import TranspilationPipeline
from py2cy.utils.exceptions import Py2CyError

@click.command()
@click.argument('input_file', type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option('--output-dir', '-o', default='cython_output', help='Directory to save the generated files.', type=click.Path(path_type=Path))
def main(input_file: Path, output_dir: Path):
    """
    A proof-of-concept tool to automatically transpile a Python file to a Cython file.
    """
    try:
        config = AppConfig()
        pipeline = TranspilationPipeline(input_file, output_dir, config)
        pipeline.run()
        click.secho("\nTranspilation successful!", fg="green")
        click.echo("To compile your new module, navigate to the output directory and run:")
        click.secho(f"  cd {output_dir}", fg="yellow")
        click.secho(f"  python setup.py build_ext --inplace", fg="yellow")
    except Py2CyError as e:
        click.secho(f"An error occurred during transpilation: {e}", fg="red")
    except Exception as e:
        click.secho(f"An unexpected error occurred: {e}", fg="red")

if __name__ == '__main__':
    main()