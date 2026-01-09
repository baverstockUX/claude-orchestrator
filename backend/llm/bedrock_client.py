"""AWS Bedrock client wrapper for Claude Sonnet 4.5."""

import json
import logging
from typing import Any, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class BedrockConfig(BaseModel):
    """Bedrock configuration."""
    profile: str = "advanced-bedrock"
    region: str = "eu-west-1"
    model_id: str = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
    max_tokens: int = 8000
    temperature: float = 1.0
    # Note: Claude Sonnet 4.5 doesn't support both temperature and top_p
    # Only use temperature


class BedrockResponse(BaseModel):
    """Response from Bedrock API."""
    content: str
    stop_reason: str
    usage: dict[str, Any]  # Can contain nested dicts for cache_creation
    model: str


class BedrockClient:
    """AWS Bedrock client for invoking Claude Sonnet 4.5."""

    def __init__(
        self,
        profile: Optional[str] = None,
        region: Optional[str] = None,
        model_id: Optional[str] = None
    ):
        """
        Initialize Bedrock client.

        Args:
            profile: AWS profile name (default: "advanced-bedrock")
            region: AWS region (default: "eu-west-1")
            model_id: Model ID (default: Claude Sonnet 4.5 inference profile)
        """
        self.config = BedrockConfig(
            profile=profile or "advanced-bedrock",
            region=region or "eu-west-1",
            model_id=model_id or "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
        )

        # Create boto3 session with profile
        session = boto3.Session(
            profile_name=self.config.profile,
            region_name=self.config.region
        )

        # Configure retry strategy
        retry_config = Config(
            region_name=self.config.region,
            retries={
                'max_attempts': 3,
                'mode': 'adaptive'
            }
        )

        # Create Bedrock runtime client
        self.client = session.client(
            service_name='bedrock-runtime',
            config=retry_config
        )

        logger.info(
            f"Initialized Bedrock client: profile={self.config.profile}, "
            f"region={self.config.region}, model={self.config.model_id}"
        )

    def invoke_model(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> BedrockResponse:
        """
        Invoke Claude model with a prompt.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate (default: 8000)
            temperature: Temperature for sampling (default: 1.0)

        Returns:
            BedrockResponse with content and metadata

        Raises:
            BedrockInvocationError: If API call fails
        """
        # Build request body
        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": messages,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature or self.config.temperature
        }

        # Add system prompt if provided
        if system_prompt:
            request_body["system"] = system_prompt

        logger.debug(
            f"Invoking model: {self.config.model_id} "
            f"(prompt_length={len(prompt)}, max_tokens={request_body['max_tokens']})"
        )

        try:
            # Invoke model
            response = self.client.invoke_model(
                modelId=self.config.model_id,
                body=json.dumps(request_body),
                contentType='application/json',
                accept='application/json'
            )

            # Parse response
            response_body = json.loads(response['body'].read())

            # Extract content from response
            content = ""
            if response_body.get("content"):
                for block in response_body["content"]:
                    if block.get("type") == "text":
                        content += block.get("text", "")

            logger.info(
                f"Model invocation successful: "
                f"stop_reason={response_body.get('stop_reason')}, "
                f"input_tokens={response_body.get('usage', {}).get('input_tokens')}, "
                f"output_tokens={response_body.get('usage', {}).get('output_tokens')}"
            )

            return BedrockResponse(
                content=content,
                stop_reason=response_body.get("stop_reason", ""),
                usage=response_body.get("usage", {}),
                model=response_body.get("model", self.config.model_id)
            )

        except (BotoCoreError, ClientError) as e:
            logger.error(f"Bedrock invocation failed: {e}")
            raise BedrockInvocationError(f"Failed to invoke model: {e}") from e

    def invoke_model_with_json_schema(
        self,
        prompt: str,
        json_schema: dict[str, Any],
        system_prompt: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Invoke model and parse response as JSON matching schema.

        Args:
            prompt: User prompt
            json_schema: Expected JSON schema for response
            system_prompt: Optional system prompt

        Returns:
            Parsed JSON response

        Raises:
            BedrockInvocationError: If API call fails
            JSONParseError: If response cannot be parsed
        """
        # Enhance prompt to request JSON output
        enhanced_prompt = f"""{prompt}

Please respond with a valid JSON object matching this schema:

```json
{json.dumps(json_schema, indent=2)}
```

Return ONLY the JSON object, no additional text."""

        response = self.invoke_model(
            prompt=enhanced_prompt,
            system_prompt=system_prompt
        )

        # Parse JSON from response
        try:
            # Try to find JSON in response (might have markdown code blocks)
            content = response.content.strip()

            # Remove markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            parsed = json.loads(content)
            logger.debug(f"Successfully parsed JSON response")
            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response content: {response.content[:500]}")
            raise JSONParseError(
                f"Failed to parse JSON from model response: {e}"
            ) from e


class BedrockInvocationError(Exception):
    """Raised when Bedrock API invocation fails."""
    pass


class JSONParseError(Exception):
    """Raised when JSON parsing fails."""
    pass
