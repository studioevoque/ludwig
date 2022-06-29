#! /usr/bin/env python
# Copyright (c) 2022 Predibase, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

import warnings
from typing import Any, Callable, Dict

from ludwig.constants import (
    DEFAULTS,
    EVAL_BATCH_SIZE,
    EXECUTOR,
    HYPEROPT,
    INPUT_FEATURES,
    NUMBER,
    OUTPUT_FEATURES,
    PARAMETERS,
    PREPROCESSING,
    RAY,
    SAMPLER,
    SCHEDULER,
    SEARCH_ALG,
    TRAINER,
    TRAINING,
    TYPE,
)
from ludwig.features.feature_registries import input_type_registry
from ludwig.utils.misc_utils import merge_dict


def _traverse_dicts(config: Any, f: Callable[[Dict], None]):
    """Applies function f to every dictionary contained in config.

    f should in-place modify the config dict. f will be called on leaves first, root last.
    """
    if isinstance(config, dict):
        for k, v in config.items():
            _traverse_dicts(v, f)
        f(config)
    elif isinstance(config, list):
        for v in config:
            _traverse_dicts(v, f)


def _upgrade_use_bias(config):
    if "bias" in config:
        warnings.warn('Parameter "bias" renamed to "use_bias" and will be removed in v0.6', DeprecationWarning)
        config["use_bias"] = config["bias"]
        del config["bias"]
    if "conv_bias" in config:
        warnings.warn(
            'Parameter "conv_bias" renamed to "conv_use_bias" and will be removed in v0.6', DeprecationWarning
        )
        config["conv_use_bias"] = config["conv_bias"]
        del config["conv_bias"]
    if "default_bias" in config:
        warnings.warn(
            'Parameter "default_bias" renamed to "default_use_bias" and will be removed in v0.6', DeprecationWarning
        )
        config["default_use_bias"] = config["default_bias"]
        del config["default_bias"]


def _upgrade_feature(feature: Dict[str, Any]):
    """Upgrades feature config (in-place)"""
    if feature.get(TYPE) == "numerical":
        warnings.warn('Feature type "numerical" renamed to "number" and will be removed in v0.6', DeprecationWarning)
        feature[TYPE] = NUMBER
    _traverse_dicts(feature, _upgrade_use_bias)


def _upgrade_hyperopt(hyperopt: Dict[str, Any]):
    """Upgrades hyperopt config (in-place)"""
    # check for use of legacy "training" reference, if any found convert to "trainer"
    if PARAMETERS in hyperopt:
        hparams = hyperopt[PARAMETERS]
        for k, v in list(hparams.items()):
            substr = "training."
            if k.startswith(substr):
                warnings.warn(
                    'Config section "training" renamed to "trainer" and will be removed in v0.6', DeprecationWarning
                )
                hparams["trainer." + k[len(substr) :]] = v
                del hparams[k]

    # check for legacy parameters in "executor"
    if EXECUTOR in hyperopt:
        hpexecutor = hyperopt[EXECUTOR]
        executor_type = hpexecutor.get(TYPE, None)
        if executor_type is not None and executor_type != RAY:
            warnings.warn(
                f'executor type "{executor_type}" not supported, converted to "ray" will be flagged as error '
                "in v0.6",
                DeprecationWarning,
            )
            hpexecutor[TYPE] = RAY

        # if search_alg not at top level and is present in executor, promote to top level
        if SEARCH_ALG in hpexecutor:
            # promote only if not in top-level, otherwise use current top-level
            if SEARCH_ALG not in hyperopt:
                hyperopt[SEARCH_ALG] = hpexecutor[SEARCH_ALG]
            del hpexecutor[SEARCH_ALG]
    else:
        warnings.warn(
            'Missing "executor" section, adding "ray" executor will be flagged as error in v0.6', DeprecationWarning
        )
        hyperopt[EXECUTOR] = {TYPE: RAY}

    # check for legacy "sampler" section
    if SAMPLER in hyperopt:
        warnings.warn(
            f'"{SAMPLER}" is no longer supported, converted to "{SEARCH_ALG}". "{SAMPLER}" will be flagged as '
            "error in v0.6",
            DeprecationWarning,
        )
        if SEARCH_ALG in hyperopt[SAMPLER]:
            if SEARCH_ALG not in hyperopt:
                hyperopt[SEARCH_ALG] = hyperopt[SAMPLER][SEARCH_ALG]
                warnings.warn('Moved "search_alg" to hyperopt config top-level', DeprecationWarning)

        # if num_samples or scheduler exist in SAMPLER move to EXECUTOR Section
        if "num_samples" in hyperopt[SAMPLER] and "num_samples" not in hyperopt[EXECUTOR]:
            hyperopt[EXECUTOR]["num_samples"] = hyperopt[SAMPLER]["num_samples"]
            warnings.warn('Moved "num_samples" from "sampler" to "executor"', DeprecationWarning)

        if SCHEDULER in hyperopt[SAMPLER] and SCHEDULER not in hyperopt[EXECUTOR]:
            hyperopt[EXECUTOR][SCHEDULER] = hyperopt[SAMPLER][SCHEDULER]
            warnings.warn('Moved "scheduler" from "sampler" to "executor"', DeprecationWarning)

        # remove legacy section
        del hyperopt[SAMPLER]

    if SEARCH_ALG not in hyperopt:
        # make top-level as search_alg, if missing put in default value
        hyperopt[SEARCH_ALG] = {TYPE: "variant_generator"}
        warnings.warn(
            'Missing "search_alg" at hyperopt top-level, adding in default value, will be flagged as error ' "in v0.6",
            DeprecationWarning,
        )


def _upgrade_trainer(trainer: Dict[str, Any]):
    """Upgrades trainer config (in-place)"""
    eval_batch_size = trainer.get(EVAL_BATCH_SIZE)
    if eval_batch_size == 0:
        warnings.warn(
            "`trainer.eval_batch_size` value `0` changed to `None`, will be unsupported in v0.6", DeprecationWarning
        )
        trainer[EVAL_BATCH_SIZE] = None


def _upgrade_preprocessing(config: Dict[str, Any]):
    """Move feature type pre-processing into the defaults section of the config (in-place)"""
    # Use input registry since it contains all feature types
    input_feature_types = set(input_type_registry.keys())
    preprocessing_params = list(config.get(PREPROCESSING).keys())
    type_specific_preprocessing_params = dict()

    for preprocessing_param in preprocessing_params:
        if preprocessing_param in input_feature_types:
            warnings.warn(
                "Moving feature-specific preprocessing configuration from `preprocessing` section to `defaults`"
                " section in Ludwig config. Support will be removed in v0.8",
                DeprecationWarning,
            )
            type_specific_preprocessing_params[preprocessing_param] = config[PREPROCESSING].pop(preprocessing_param)

    if DEFAULTS not in config:
        config[DEFAULTS] = dict()

    for feature_type, preprocessing_param in type_specific_preprocessing_params.items():
        if feature_type not in config.get(DEFAULTS):
            config[DEFAULTS][feature_type] = preprocessing_param
        elif PREPROCESSING not in config[DEFAULTS][feature_type]:
            config[DEFAULTS][feature_type][PREPROCESSING] = preprocessing_param[PREPROCESSING]
        else:
            config[DEFAULTS][feature_type][PREPROCESSING].update(
                merge_dict(config[DEFAULTS][feature_type][PREPROCESSING], preprocessing_param[PREPROCESSING])
            )


def upgrade_deprecated_fields(config: Dict[str, Any]):
    """Updates config (in-place) to use fields from earlier versions of Ludwig.

    Logs deprecation warnings
    """
    if TRAINING in config:
        warnings.warn('Config section "training" renamed to "trainer" and will be removed in v0.6', DeprecationWarning)
        config[TRAINER] = config[TRAINING]
        del config[TRAINING]

    for feature in config.get(INPUT_FEATURES, []) + config.get(OUTPUT_FEATURES, []):
        _upgrade_feature(feature)

    if HYPEROPT in config:
        _upgrade_hyperopt(config[HYPEROPT])

    if TRAINER in config:
        _upgrade_trainer(config[TRAINER])

    if PREPROCESSING in config:
        _upgrade_preprocessing(config)
