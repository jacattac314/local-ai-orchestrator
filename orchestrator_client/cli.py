"""
Orchestrator CLI Tool
Command-line interface for the AI Orchestrator.
"""

import json
import sys
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .client import OrchestratorClient


console = Console()


def get_client(url: str, api_key: Optional[str] = None) -> OrchestratorClient:
    """Create a client instance."""
    return OrchestratorClient(base_url=url, api_key=api_key)


@click.group()
@click.option("--url", "-u", default="http://localhost:8000", help="API server URL")
@click.option("--api-key", "-k", envvar="ORCHESTRATOR_API_KEY", help="API key")
@click.pass_context
def cli(ctx, url: str, api_key: Optional[str]):
    """AI Orchestrator CLI - Smart model routing for AI applications."""
    ctx.ensure_object(dict)
    ctx.obj["url"] = url
    ctx.obj["api_key"] = api_key


@cli.command()
@click.pass_context
def health(ctx):
    """Check API server health."""
    with get_client(ctx.obj["url"], ctx.obj["api_key"]) as client:
        try:
            status = client.health()
            if status.get("status") == "healthy":
                console.print("✅ [green]API is healthy[/green]")
                console.print(f"   Models: {status.get('model_count', 0)}")
                console.print(f"   Database: {status.get('db_status', 'unknown')}")
            else:
                console.print("⚠️ [yellow]API status unknown[/yellow]")
        except Exception as e:
            console.print(f"❌ [red]Connection failed: {e}[/red]")
            sys.exit(1)


@cli.command()
@click.option("--profile", "-p", default="balanced", help="Routing profile")
@click.option("--limit", "-n", default=10, help="Number of models to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def rankings(ctx, profile: str, limit: int, as_json: bool):
    """Show model rankings for a routing profile."""
    with get_client(ctx.obj["url"], ctx.obj["api_key"]) as client:
        try:
            models = client.get_rankings(profile=profile, limit=limit)
            
            if as_json:
                data = [
                    {
                        "rank": i + 1,
                        "model": m.model_name,
                        "score": round(m.composite_score, 3),
                        "quality": round(m.quality_score, 3),
                        "latency": round(m.latency_score, 3),
                        "cost": round(m.cost_score, 3),
                    }
                    for i, m in enumerate(models)
                ]
                console.print(json.dumps(data, indent=2))
                return
            
            table = Table(title=f"Model Rankings ({profile} profile)")
            table.add_column("#", style="dim", width=4)
            table.add_column("Model", style="cyan")
            table.add_column("Score", justify="right", style="green")
            table.add_column("Quality", justify="right")
            table.add_column("Latency", justify="right")
            table.add_column("Cost", justify="right")
            
            for i, m in enumerate(models):
                score_color = "green" if m.composite_score > 0.8 else "yellow" if m.composite_score > 0.6 else "red"
                table.add_row(
                    str(i + 1),
                    m.model_name.split("/")[-1],
                    f"[{score_color}]{m.composite_score:.0%}[/{score_color}]",
                    f"{m.quality_score:.0%}",
                    f"{m.latency_score:.0%}",
                    f"{m.cost_score:.0%}",
                )
            
            console.print(table)
            
        except Exception as e:
            console.print(f"❌ [red]Error: {e}[/red]")
            sys.exit(1)


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def profiles(ctx, as_json: bool):
    """List available routing profiles."""
    with get_client(ctx.obj["url"], ctx.obj["api_key"]) as client:
        try:
            profile_list = client.get_profiles()
            
            if as_json:
                data = [
                    {
                        "name": p.name,
                        "quality_weight": p.quality_weight,
                        "latency_weight": p.latency_weight,
                        "cost_weight": p.cost_weight,
                    }
                    for p in profile_list
                ]
                console.print(json.dumps(data, indent=2))
                return
            
            table = Table(title="Routing Profiles")
            table.add_column("Profile", style="cyan")
            table.add_column("Quality", justify="right")
            table.add_column("Latency", justify="right")
            table.add_column("Cost", justify="right")
            table.add_column("Constraints")
            
            for p in profile_list:
                constraints = []
                if p.min_quality:
                    constraints.append(f"min_quality={p.min_quality:.0%}")
                if p.max_latency_ms:
                    constraints.append(f"max_latency={p.max_latency_ms}ms")
                if p.max_cost_per_million:
                    constraints.append(f"max_cost=${p.max_cost_per_million}")
                
                table.add_row(
                    p.name,
                    f"{p.quality_weight:.0%}",
                    f"{p.latency_weight:.0%}",
                    f"{p.cost_weight:.0%}",
                    ", ".join(constraints) if constraints else "-",
                )
            
            console.print(table)
            
        except Exception as e:
            console.print(f"❌ [red]Error: {e}[/red]")
            sys.exit(1)


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def models(ctx, as_json: bool):
    """List all available models."""
    with get_client(ctx.obj["url"], ctx.obj["api_key"]) as client:
        try:
            model_list = client.list_models()
            
            if as_json:
                console.print(json.dumps(model_list, indent=2))
                return
            
            table = Table(title=f"Available Models ({len(model_list)})")
            table.add_column("Model", style="cyan")
            table.add_column("Provider")
            table.add_column("Context", justify="right")
            
            for m in model_list[:20]:  # Show first 20
                name = m.get("name", "")
                parts = name.split("/")
                provider = parts[0] if len(parts) > 1 else "unknown"
                model_name = parts[-1]
                context = m.get("context_length", 0)
                
                table.add_row(
                    model_name,
                    provider.title(),
                    f"{context:,}" if context else "-",
                )
            
            console.print(table)
            if len(model_list) > 20:
                console.print(f"[dim]... and {len(model_list) - 20} more models[/dim]")
            
        except Exception as e:
            console.print(f"❌ [red]Error: {e}[/red]")
            sys.exit(1)


@cli.command()
@click.argument("message")
@click.option("--model", "-m", default="auto", help="Model to use (default: auto)")
@click.option("--profile", "-p", default="balanced", help="Routing profile")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def chat(ctx, message: str, model: str, profile: str, as_json: bool):
    """Send a chat message and get a response."""
    with get_client(ctx.obj["url"], ctx.obj["api_key"]) as client:
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                progress.add_task("Routing and generating...", total=None)
                response = client.chat(message, model=model, profile=profile)
            
            if as_json:
                console.print(json.dumps({
                    "model": response.model,
                    "content": response.content,
                    "usage": response.usage,
                }, indent=2))
                return
            
            console.print(Panel(
                response.content,
                title=f"[cyan]{response.model}[/cyan]",
                border_style="green",
            ))
            
            if response.usage:
                tokens = response.usage.get("total_tokens", 0)
                console.print(f"[dim]Tokens: {tokens}[/dim]")
            
        except Exception as e:
            console.print(f"❌ [red]Error: {e}[/red]")
            sys.exit(1)


@cli.command()
@click.option("--profile", "-p", default="balanced", help="Routing profile")
@click.pass_context
def route(ctx, profile: str):
    """Get the best model for a profile (quick lookup)."""
    with get_client(ctx.obj["url"], ctx.obj["api_key"]) as client:
        try:
            best = client.get_best_model(profile=profile)
            if best:
                console.print(f"[green]{best.model_name}[/green] (score: {best.composite_score:.0%})")
            else:
                console.print("[yellow]No models available[/yellow]")
        except Exception as e:
            console.print(f"❌ [red]Error: {e}[/red]")
            sys.exit(1)


@cli.command()
@click.option("--period", "-p", default="24h", help="Time period (1h, 24h, 7d, 30d)")
@click.pass_context
def analytics(ctx, period: str):
    """Show usage analytics summary."""
    with get_client(ctx.obj["url"], ctx.obj["api_key"]) as client:
        try:
            summary = client.get_analytics_summary(period=period)
            
            table = Table(title=f"Analytics Summary ({period})")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right")
            
            table.add_row("Total Requests", f"{summary.total_requests:,}")
            table.add_row("Total Tokens", f"{summary.total_tokens:,}")
            table.add_row("Estimated Cost", f"${summary.estimated_cost:.2f}")
            table.add_row("Avg Latency", f"{summary.avg_latency_ms:.0f}ms")
            
            console.print(table)
            
            if summary.top_models:
                console.print("\n[bold]Top Models:[/bold]")
                for i, m in enumerate(summary.top_models[:5], 1):
                    console.print(f"  {i}. {m.get('model', 'unknown')} ({m.get('count', 0)} requests)")
            
        except Exception as e:
            console.print(f"❌ [red]Error: {e}[/red]")
            sys.exit(1)


def main():
    """CLI entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
