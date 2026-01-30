# Contributing to Local AI Orchestrator

Thank you for your interest in contributing to the Local AI Orchestrator project! This document provides guidelines and instructions for contributing.

## Code of Conduct

We are committed to providing a welcoming and inspiring community for all. Please read and adhere to our community standards in all interactions.

## Getting Started

### Development Setup

1. **Clone the repository**
2.    ```bash
         git clone https://github.com/jacattac314/local-ai-orchestrator.git
         cd local-ai-orchestrator
         ```

      2. **Install dependencies**
      3.    ```bash
               make install
               ```

            3. **Set up environment variables**
            4.    ```bash
                     cp .env.example .env
                     # Edit .env with your configuration
                     ```

                  4. **Run tests locally**
                  5.    ```bash
                           make test
                           ```

                        ### Project Structure

                    - `src/orchestrator/` - Main orchestrator package
                    - - `orchestrator_client/` - Python SDK and CLI
                      - - `frontend/` - Web dashboard
                        - - `tests/` - Test suite
                          - - `docs/` - Documentation
                           
                            - ## Contribution Workflow
                           
                            - ### 1. Create an Issue
                           
                            - Before starting work, please create an issue to discuss what you want to implement. This helps prevent duplicate work and ensures alignment with project goals.
                           
                            - ### 2. Fork and Branch
                           
                            - ```bash
                              git checkout -b feature/your-feature-name
                              # or
                              git checkout -b fix/issue-number
                              ```

                              **Branch naming conventions:**
                              - Features: `feature/descriptive-name`
                              - - Bug fixes: `fix/descriptive-name`
                                - - Documentation: `docs/descriptive-name`
                                  - - Refactoring: `refactor/descriptive-name`
                                   
                                    - ### 3. Commit Messages
                                   
                                    - Follow conventional commits format:
                                   
                                    - ```
                                      <type>(<scope>): <subject>

                                      <body>

                                      <footer>
                                      ```

                                      **Types:**
                                      - `feat`: A new feature
                                      - - `fix`: A bug fix
                                        - - `docs`: Documentation changes
                                          - - `style`: Code style changes (formatting, semicolons, etc.)
                                            - - `refactor`: Code refactoring without feature changes
                                              - - `perf`: Performance improvements
                                                - - `test`: Adding or updating tests
                                                  - - `chore`: Build process, dependency updates, etc.
                                                   
                                                    - **Examples:**
                                                    - ```
                                                      feat(routing): add dynamic model selection based on complexity

                                                      fix(api): handle null model responses correctly

                                                      docs(api): update endpoint documentation with examples

                                                      refactor(db): simplify database query logic
                                                      ```

                                                      ### 4. Code Style

                                                      The project uses automated code quality tools:

                                                      - **Linting**: `ruff` - Python code style
                                                      - - **Formatting**: `black` - Code formatter
                                                        - - **Type Checking**: `mypy` - Static type checking
                                                          - - **Pre-commit hooks**: Run automatically before commits
                                                           
                                                            - Run these manually:
                                                            - ```bash
                                                              make lint     # Run ruff and mypy
                                                              make format   # Format code with black
                                                              ```

                                                              ### 5. Testing

                                                              We require tests for all changes:

                                                              ```bash
                                                              # Run all tests
                                                              make test

                                                              # Run specific test markers
                                                              poetry run pytest -m canary        # Fast CI/CD tests
                                                              poetry run pytest -m integration   # Integration tests
                                                              poetry run pytest -m performance   # Performance benchmarks
                                                              ```

                                                              **Test file naming:**
                                                              - Unit tests: `test_<module_name>.py`
                                                              - - Integration tests: Mark with `@pytest.mark.integration`
                                                                - - Performance tests: Mark with `@pytest.mark.performance`
                                                                  - - Canary tests: Mark with `@pytest.mark.canary`
                                                                   
                                                                    - ### 6. Documentation
                                                                   
                                                                    - Update relevant documentation:
                                                                   
                                                                    - - **API changes**: Update endpoint descriptions and examples
                                                                      - - **Configuration**: Update `.env.example` and config documentation
                                                                        - - **Features**: Update `README.md` and API documentation
                                                                         
                                                                          - Use Google-style docstrings:
                                                                         
                                                                          - ```python
                                                                            def route_request(request: ChatCompletionRequest, profile: str) -> str:
                                                                                """Route a request to the best model based on routing profile.

                                                                                Routes incoming requests to the optimal model based on the specified
                                                                                routing profile (quality, balanced, speed, budget, long_context).
                                                                                Falls back to next-ranked model on failures.

                                                                                Args:
                                                                                    request: The chat completion request to route
                                                                                    profile: Routing profile name. Defaults to 'balanced'

                                                                                Returns:
                                                                                    The selected model name

                                                                                Raises:
                                                                                    ValueError: If the routing profile is not recognized
                                                                                    HTTPException: If all models fail after retries

                                                                                Example:
                                                                                    >>> request = ChatCompletionRequest(messages=[...])
                                                                                    >>> model = route_request(request, profile='quality')
                                                                                    >>> print(model)
                                                                                    "gpt-4"
                                                                                """
                                                                            ```

                                                                            ## Pull Request Process

                                                                            ### Before Submitting

                                                                            1. **Update your branch**: `git rebase main`
                                                                            2. 2. **Run tests**: `make test`
                                                                               3. 3. **Check formatting**: `make format lint`
                                                                                  4. 4. **Update documentation**: If applicable
                                                                                    
                                                                                     5. ### PR Description
                                                                                    
                                                                                     6. Include:
                                                                                    
                                                                                     7. - **Description**: What problem does this solve?
                                                                                        - - **Type of change**: Feature, bugfix, documentation, etc.
                                                                                          - - **Related issues**: Link to issue #123 with `Closes #123`
                                                                                            - - **Testing**: How was this tested?
                                                                                              - - **Screenshots**: For UI changes
                                                                                               
                                                                                                - ### PR Title Format
                                                                                               
                                                                                                - Follow conventional commits:
                                                                                                - ```
                                                                                                  feat(scope): description
                                                                                                  fix(scope): description
                                                                                                  ```

                                                                                                  ### Code Review

                                                                                                  - At least one approval required to merge
                                                                                                  - - All CI/CD checks must pass
                                                                                                    - - Address feedback and re-request review
                                                                                                      - - Keep commits organized and squash if necessary
                                                                                                       
                                                                                                        - ## Reporting Bugs
                                                                                                       
                                                                                                        - Submit bug reports through GitHub Issues:
                                                                                                       
                                                                                                        - 1. **Check existing issues** - Avoid duplicates
                                                                                                          2. 2. **Provide reproduction steps** - Specific, detailed steps
                                                                                                             3. 3. **Include environment info**:
                                                                                                                4.    - Python version
                                                                                                                      -    - OS/Platform
                                                                                                                           -    - Relevant dependency versions
                                                                                                                                - 4. **Share logs** - Relevant error logs or stack traces
                                                                                                                                 
                                                                                                                                  5. Template:
                                                                                                                                  6. ```
                                                                                                                                     **Describe the bug**
                                                                                                                                     Clear description of what happened

                                                                                                                                     **Steps to reproduce**
                                                                                                                                     1. ...
                                                                                                                                     2. ...
                                                                                                                                     3. ...

                                                                                                                                     **Expected behavior**
                                                                                                                                     What should have happened

                                                                                                                                     **Actual behavior**
                                                                                                                                     What actually happened

                                                                                                                                     **Environment**
                                                                                                                                     - Python: 3.11
                                                                                                                                     - OS: Ubuntu 22.04
                                                                                                                                     - Dependencies: See output of `pip freeze`

                                                                                                                                     **Logs**
                                                                                                                                     ```
                                                                                                                                     Error output here
                                                                                                                                     ```
                                                                                                                                     ```
                                                                                                                                     
                                                                                                                                     ## Feature Requests
                                                                                                                                     
                                                                                                                                     Submit feature requests through GitHub Issues:
                                                                                                                                     
                                                                                                                                     1. **Clear title** - Briefly describe the feature
                                                                                                                                     2. 2. **Use case** - Why is this feature needed?
                                                                                                                                        3. 3. **Proposed solution** - How should it work?
                                                                                                                                           4. 4. **Alternatives** - Other approaches considered
                                                                                                                                             
                                                                                                                                              5. ## Development Commands
                                                                                                                                             
                                                                                                                                              6. ```bash
                                                                                                                                                 # Installation and setup
                                                                                                                                                 make install        # Install dependencies
                                                                                                                                                 make install-pre-commit  # Setup pre-commit hooks

                                                                                                                                                 # Code quality
                                                                                                                                                 make lint           # Check code style with ruff and mypy
                                                                                                                                                 make format         # Format code with black and ruff

                                                                                                                                                 # Testing
                                                                                                                                                 make test           # Run all tests
                                                                                                                                                 make test-coverage  # Run tests with coverage

                                                                                                                                                 # Running locally
                                                                                                                                                 make run            # Start development server
                                                                                                                                                 make clean          # Clean cache and build artifacts
                                                                                                                                                 ```
                                                                                                                                                 
                                                                                                                                                 ## Release Process
                                                                                                                                                 
                                                                                                                                                 1. Update version in `pyproject.toml`
                                                                                                                                                 2. 2. Update `CHANGELOG.md`
                                                                                                                                                    3. 3. Create a git tag: `git tag v1.2.3`
                                                                                                                                                       4. 4. Push tag: `git push origin v1.2.3`
                                                                                                                                                          5. 5. GitHub Actions will build and publish
                                                                                                                                                            
                                                                                                                                                             6. ## Performance Considerations
                                                                                                                                                            
                                                                                                                                                             7. When contributing, keep in mind:
                                                                                                                                                            
                                                                                                                                                             8. - **Routing latency** - Minimize decision time for model routing
                                                                                                                                                                - - **Memory usage** - Cache efficiently without excessive memory footprint
                                                                                                                                                                  - - **Database queries** - Avoid N+1 query problems
                                                                                                                                                                    - - **API calls** - Cache external data appropriately
                                                                                                                                                                     
                                                                                                                                                                      - ## Questions or Need Help?
                                                                                                                                                                     
                                                                                                                                                                      - - **GitHub Issues**: For bug reports and feature requests
                                                                                                                                                                        - - **GitHub Discussions**: For questions and ideas
                                                                                                                                                                          - - **Documentation**: See `docs/` directory for detailed guides
                                                                                                                                                                           
                                                                                                                                                                            - ## Additional Resources
                                                                                                                                                                           
                                                                                                                                                                            - - [Architecture Documentation](docs/ARCHITECTURE.md)
                                                                                                                                                                              - - [API Documentation](docs/API.md)
                                                                                                                                                                                - - [Deployment Guide](docs/DEPLOYMENT.md)
                                                                                                                                                                                  - - [Security Policy](SECURITY.md)
                                                                                                                                                                                   
                                                                                                                                                                                    - ## License
                                                                                                                                                                                   
                                                                                                                                                                                    - By contributing, you agree that your contributions will be licensed under the MIT License.
