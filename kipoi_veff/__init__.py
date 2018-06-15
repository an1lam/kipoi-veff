from __future__ import absolute_import

__author__ = 'Kipoi team'
__email__ = 'avsec@in.tum.de'
__version__ = '0.1.0'


from kipoi.postprocessing.variant_effects.scores import Ref, Alt, Diff, LogitRef, LogitAlt, Logit, DeepSEA_effect
from .parsers import KipoiVCFParser
from .snv_predict import predict_snvs, analyse_model_preds, score_variants
from .utils import ModelInfoExtractor, SnvPosRestrictedRg, SnvCenteredRg, ensure_tabixed_vcf, VcfWriter, \
    BedOverlappingRg
from .mutation_map import MutationMap
# from .mutation_map import _generate_mutation_map, MutationMapDrawer