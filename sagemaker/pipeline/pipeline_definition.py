from __future__ import annotations

import argparse
import json
from pathlib import Path

import boto3
from sagemaker.inputs import TrainingInput
from sagemaker.model_metrics import MetricsSource, ModelMetrics
from sagemaker.processing import ProcessingInput, ProcessingOutput, ScriptProcessor
from sagemaker.sklearn.estimator import SKLearn
from sagemaker.sklearn.model import SKLearnModel
from sagemaker.session import Session
from sagemaker.workflow.model_step import ModelStep
from sagemaker.workflow.parameters import ParameterInteger, ParameterString
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.pipeline_context import PipelineSession
from sagemaker.workflow.properties import PropertyFile
from sagemaker.workflow.steps import ProcessingStep, TrainingStep
from sagemaker.workflow.step_collections import RegisterModel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update the SageMaker pipeline for agri-price training.")
    parser.add_argument("--region", default=boto3.session.Session().region_name)
    parser.add_argument("--role-arn", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--features-prefix", default="processed/features/")
    parser.add_argument("--pipeline-name", default="agri-price-train-evaluate-register")
    parser.add_argument("--model-package-group-name", default="agri-price-multi-output")
    parser.add_argument("--default-instance-type", default="ml.m5.xlarge")
    parser.add_argument("--framework-version", default="1.2-1")
    parser.add_argument("--python-version", default="py3")
    parser.add_argument("--code-bundle-s3-uri", required=True)
    parser.add_argument("--evaluate-script-s3-uri", required=True)
    parser.add_argument("--output-json", default="")
    return parser.parse_args()


def build_pipeline(args: argparse.Namespace) -> Pipeline:
    boto_session = boto3.session.Session(region_name=args.region)
    pipeline_session = PipelineSession(boto_session=boto_session, sagemaker_client=boto_session.client("sagemaker"), default_bucket=args.bucket)

    training_instance_type = ParameterString(name="TrainingInstanceType", default_value=args.default_instance_type)
    processing_instance_type = ParameterString(name="ProcessingInstanceType", default_value=args.default_instance_type)
    target_columns = ParameterString(name="TargetColumns", default_value="")
    train_input_s3_uri = ParameterString(name="FeaturesS3Uri", default_value=f"s3://{args.bucket}/{args.features_prefix}")
    approval_status = ParameterString(name="ModelApprovalStatus", default_value="PendingManualApproval")
    validation_fraction = ParameterString(name="ValidationFraction", default_value="0.2")
    min_validation_rows = ParameterInteger(name="MinValidationRows", default_value=14)
    min_training_rows = ParameterInteger(name="MinTrainingRows", default_value=30)
    walk_forward_windows = ParameterInteger(name="WalkForwardWindows", default_value=3)

    estimator = SKLearn(
        entry_point="train.py",
        source_dir=args.code_bundle_s3_uri,
        role=args.role_arn,
        framework_version=args.framework_version,
        py_version=args.python_version,
        instance_type=training_instance_type,
        instance_count=1,
        sagemaker_session=pipeline_session,
        hyperparameters={
            "target-columns": target_columns,
            "validation-fraction": validation_fraction,
            "min-validation-rows": min_validation_rows,
            "min-training-rows": min_training_rows,
            "walk-forward-windows": walk_forward_windows,
        },
        output_path=f"s3://{args.bucket}/sagemaker/training-output/",
    )

    train_step = TrainingStep(
        name="TrainMultiOutputModel",
        estimator=estimator,
        inputs={"training": TrainingInput(s3_data=train_input_s3_uri, content_type="application/x-parquet")},
    )

    evaluator = ScriptProcessor(
        image_uri=estimator.training_image_uri(),
        command=["python"],
        role=args.role_arn,
        instance_count=1,
        instance_type=processing_instance_type,
        sagemaker_session=pipeline_session,
    )

    evaluation_report = PropertyFile(name="EvaluationReport", output_name="evaluation", path="evaluation.json")
    eval_step = ProcessingStep(
        name="EvaluateMultiOutputModel",
        processor=evaluator,
        code=args.evaluate_script_s3_uri,
        job_arguments=[
            "--features-path",
            "/opt/ml/processing/input/features",
            "--model-path",
            "/opt/ml/processing/model/model.pkl",
            "--output-path",
            "/opt/ml/processing/evaluation/evaluation.json",
            "--target-columns",
            target_columns,
            "--validation-fraction",
            validation_fraction,
            "--min-validation-rows",
            str(min_validation_rows.default_value),
            "--min-training-rows",
            str(min_training_rows.default_value),
        ],
        inputs=[
            ProcessingInput(source=train_input_s3_uri, destination="/opt/ml/processing/input/features"),
            ProcessingInput(source=train_step.properties.ModelArtifacts.S3ModelArtifacts, destination="/opt/ml/processing/model"),
        ],
        outputs=[ProcessingOutput(output_name="evaluation", source="/opt/ml/processing/evaluation")],
        property_files=[evaluation_report],
    )

    model = SKLearnModel(
        model_data=train_step.properties.ModelArtifacts.S3ModelArtifacts,
        role=args.role_arn,
        framework_version=args.framework_version,
        py_version=args.python_version,
        entry_point="inference.py",
        source_dir=args.code_bundle_s3_uri,
        sagemaker_session=pipeline_session,
    )

    model_metrics = ModelMetrics(
        model_statistics=MetricsSource(
            s3_uri=eval_step.properties.ProcessingOutputConfig.Outputs["evaluation"].S3Output.S3Uri,
            content_type="application/json",
        )
    )

    register_step = RegisterModel(
        name="RegisterMultiOutputModel",
        estimator=estimator,
        model_data=train_step.properties.ModelArtifacts.S3ModelArtifacts,
        content_types=["application/json"],
        response_types=["application/json"],
        inference_instances=["ml.m5.large"],
        transform_instances=["ml.m5.large"],
        model_package_group_name=args.model_package_group_name,
        approval_status=approval_status,
        model_metrics=model_metrics,
    )

    return Pipeline(
        name=args.pipeline_name,
        parameters=[
            training_instance_type,
            processing_instance_type,
            target_columns,
            train_input_s3_uri,
            approval_status,
            validation_fraction,
            min_validation_rows,
            min_training_rows,
            walk_forward_windows,
        ],
        steps=[train_step, eval_step, register_step],
        sagemaker_session=pipeline_session,
    )


def main() -> None:
    args = parse_args()
    pipeline = build_pipeline(args)
    definition = pipeline.definition()
    if args.output_json:
        Path(args.output_json).write_text(definition, encoding="utf-8")
    else:
        print(definition)


if __name__ == "__main__":
    main()
