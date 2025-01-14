import copy
import os
import sys
import warnings

import cyvcf2
import numpy as np
import pandas as pd
import pybedtools as pb
import pytest
from scipy.special import logit

import config
import kipoi
import kipoi_veff
import kipoi_veff as ve
import kipoi_veff.snv_predict as sp
import kipoi_veff.utils.generic
import kipoi_veff.utils.io
from kipoi.metadata import GenomicRanges
from kipoi.pipeline import install_model_requirements
from kipoi_veff import analyse_model_preds
from kipoi_veff.scores import Logit, LogitRef, LogitAlt, Diff, DeepSEA_effect, RCScore, scoring_options
from kipoi_veff.utils.mutators import rc_str, _modify_single_string_base
from kipoi_veff.utils import is_indel_wrapper
from kipoi_veff.snv_predict import homogenise_seqname
from kipoi_veff.utils.io import SyncBatchWriter
import os
import copy

warnings.filterwarnings('ignore')

from kipoi.specs import ArraySchema, ModelSchema
from related import from_yaml
from kipoi_veff.utils import OutputReshaper
from utils import compare_vcfs, temp

CLS = ArraySchema
MS = ModelSchema

RES = {}
RES["2darray_NoLab"] = np.zeros((50, 2))
RES["2darray_Lab"] = np.zeros((50, 2))
RES["list1D_NoLab"] = [np.zeros((50, 1)), np.zeros((50, 1))]
RES["list1D_Lab"] = [np.zeros((50, 1)), np.zeros((50, 1))]
RES["listMixed_NoLab"] = [np.zeros((50, 2)), np.zeros((50, 1))]
RES["listMixed_Lab"] = [np.zeros((50, 2)), np.zeros((50, 1))]
RES["dictMixed_NoLab"] = {"A": np.zeros((50, 2)), "B": np.zeros((50, 1))}
RES["dictMixed_Lab"] = {"A": np.zeros((50, 2)), "B": np.zeros((50, 1))}

RES_OUT_SHAPES = {}
RES_OUT_SHAPES["2darray_NoLab"] = 2
RES_OUT_SHAPES["2darray_Lab"] = 2
RES_OUT_SHAPES["list1D_NoLab"] = 2
RES_OUT_SHAPES["list1D_Lab"] = 2
RES_OUT_SHAPES["listMixed_NoLab"] = 3
RES_OUT_SHAPES["listMixed_Lab"] = 3
RES_OUT_SHAPES["dictMixed_NoLab"] = 3
RES_OUT_SHAPES["dictMixed_Lab"] = 3

RES_OUT_LABELS = {'dictMixed_Lab': ['A.blablabla', 'A.blaSecond', 'B.blaThird'],
                  'list1D_Lab': ['A.blablabla', 'B.blaSecond'], 'listMixed_NoLab':
                      ['0.0', '0.1', '1.0'], '2darray_Lab': ['rbp_prb', 'second'],
                  'dictMixed_NoLab': ['B.0', 'A.0', 'A.1'], 'list1D_NoLab': ['0.0', '1.0'],
                  '2darray_NoLab': ['0', '1'], 'listMixed_Lab':
                      ['A.blablabla', 'A.blaSecond', 'B.blaThird']}

YAMLS = {}
YAMLS["2darray_Lab"] = """
inputs:
  A:
    shape: (101, 4)
    doc: abjhdbajd
targets:
    shape: (2, )
    doc: Predicted binding strength
    name: A
    column_labels:
        - rbp_prb
        - second"""

YAMLS["2darray_NoLab"] = """
inputs:
  A:
    shape: (101, 4)
    doc: abjhdbajd
targets:
    shape: (2, )
    doc: Predicted binding strength"""

YAMLS["list1D_NoLab"] = """
inputs:
  A:
    shape: (101, 4)
    doc: abjhdbajd
targets:
  - shape: (1, )
    doc: Predicted binding strength
  - shape: (1, )
    doc: Predicted binding strength
    """
YAMLS["list1D_Lab"] = """
inputs:
  A:
    shape: (101, 4)
    doc: abjhdbajd
targets:
  - shape: (1, )
    name: A 
    doc: Predicted binding strength
    column_labels:
      - blablabla
  - shape: (1, )
    name: B
    doc: Predicted binding strength
    column_labels:
      - blaSecond
    """

YAMLS["listMixed_Lab"] = """
inputs:
  A:
    shape: (101, 4)
    doc: abjhdbajd
targets:
  - shape: (2, )
    name: A
    doc: Predicted binding strength
    column_labels:
      - blablabla
      - blaSecond
  - shape: (1, )
    name: B
    doc: Predicted binding strength
    column_labels:
      - blaThird
    """

YAMLS["listMixed_NoLab"] = """
inputs:
  A:
    shape: (101, 4)
    doc: abjhdbajd
targets:
  - shape: (2, )
    doc: Predicted binding strength
  - shape: (1, )
    doc: Predicted binding strength
    """

YAMLS["dictMixed_Lab"] = """
inputs:
  A:
    shape: (101, 4)
    doc: abjhdbajd
targets:
  A:
    shape: (2, )
    doc: Predicted binding strength
    column_labels:
      - blablabla
      - blaSecond
  B:
    shape: (1, )
    doc: Predicted binding strength
    column_labels:
      - blaThird
    """

YAMLS["dictMixed_NoLab"] = """
inputs:
  A:
    shape: (101, 4)
    doc: abjhdbajd
targets:
  B:
    shape: (1, )
    doc: Predicted binding strength
  A:
    shape: (2, )
    doc: Predicted binding strength
    """

# TODO: We still need a way to get the model output annotation from somewhere...
# TODO: which other arguments should we use for variant effect predictions?
# Only viable model at the moment is rbp, so not offering to test anything else
# INSTALL_REQ = True
INSTALL_REQ = config.install_req


class dummy_container(object):
    pass


class DummyModelInfo(object):

    def __init__(self, seq_length):
        self.seq_length = seq_length

    def get_seq_len(self):
        return self.seq_length


def test_ism():
    # Here we should have a simple dummy model, at the moment tested in test_var_eff_pred
    pass


def test__annotate_vcf():
    # This is tested in test_var_eff_pred
    pass


def test__modify_bases():
    # actually modify the bases of a numpy array
    # test whether samples that are included in `lines` are left untouched.
    seq_len = 101
    var_pos = np.array([1, 2, 3, 4, 5])
    alphabet = np.array(['A', "C", "G", "T"])
    new_base = np.array(['A', "C", "G", "T", "T"])
    lines = np.array([0, 5, 2, 1, 3])
    is_rc_vec = np.zeros((5)) == 1
    is_rc_vec[[1, 2]] = True
    for is_rc in [False, True]:
        empty_input = np.zeros((6, seq_len, 4)) - 1
        if is_rc:
            is_rc_vec = ~is_rc_vec
        warn_lines = ve.utils.mutators._modify_bases(empty_input, lines, var_pos, new_base, is_rc_vec)
        assert len(warn_lines) == 0
        empty_input[lines[is_rc_vec], ...] = empty_input[lines[is_rc_vec], ::-1, ::-1]
        untouched_lines = np.where(~np.in1d(np.arange(empty_input.shape[0]), lines))[0]
        assert np.all(empty_input[lines, ...].sum(axis=1).sum(axis=1) == ((-101) * 4 + 4 + 1))
        assert np.all(empty_input[untouched_lines, ...] == -1)
        for p, b, l in zip(var_pos, new_base, lines):
            base_sel = alphabet == b
            assert empty_input[l, p, base_sel] == 1
            assert np.all(empty_input[l, p, ~base_sel] == 0)
            assert np.all(empty_input[l, ~np.in1d(np.arange(seq_len), [p]), :] == -1)
    # test the warning when the reference base is wrong.
    input_set = ["AGTGTCGT", "AGTGTCGT", "AGTGTCGT"]
    input_set_onehot = np.array([onehot(el) for el in input_set])
    preproc_conv_bad = {"pp_line": [0, 1, 2], "varpos_rel": [2, np.nan, 3], "ref": ["T", np.nan, "G"],
                        "alt": ["n", np.nan, "t"],
                        "start": [0, np.nan, 0], "end": [7, np.nan, 7], "id": ["a", "b", "c"],
                        "do_mutate": [True, False, True],
                        "strand": ["+", np.nan, "-"]}
    ppcb_df = pd.DataFrame(preproc_conv_bad).query("do_mutate")
    warn_lines = ve.utils.mutators._modify_bases(input_set_onehot, ppcb_df["pp_line"].values,
                                                 ppcb_df["varpos_rel"].values.astype(np.int),
                                                 ppcb_df["ref"].str.upper().values, ppcb_df["strand"].values == "-",
                                                 return_ref_warning=True)
    assert warn_lines == [2]
    mut_set = [one_hot2string(input_set_onehot[i, ...]) for i in range(input_set_onehot.shape[0])]
    ref_mut_set = ["AGTGTCGT", "AGTGTCGT", "AGTGCCGT"]
    assert mut_set == ref_mut_set
    # Now test if the "N" is converted to 0:
    input_set_onehot = np.array([onehot(el) for el in input_set])
    warn_lines = ve.utils.mutators._modify_bases(input_set_onehot, ppcb_df["pp_line"].values,
                                                 ppcb_df["varpos_rel"].values.astype(np.int),
                                                 ppcb_df["alt"].str.upper().values, ppcb_df["strand"].values == "-",
                                                 return_ref_warning=True)
    assert np.all(input_set_onehot[0, 2, :] == 0)
    assert np.all(input_set_onehot[2, 4, 0] == 1)  # A
    assert np.all(input_set_onehot[2, 4, 1:] == 0)  # A


def test__get_seq_fields():
    model_dir = "tests/models/rbp/"
    assert (
        kipoi_veff.utils.generic._get_seq_fields(
            kipoi.get_model_descr(model_dir, source="dir")) == ['seq'])
    model_dir = "tests/models/extended_coda/"
    with pytest.raises(Exception):
        kipoi_veff.utils.generic._get_seq_fields(
            kipoi.get_model_descr(model_dir, source="dir"))


def test__get_dl_bed_fields():
    model_dir = "tests/models/rbp/"
    assert (
        kipoi_veff.utils.generic._get_dl_bed_fields(
            kipoi.get_dataloader_descr(model_dir, source="dir")) == ['intervals_file'])

def test_dna_reshaper():
    for n_seqs in [1, 3, 500]:
        for seq_len in [101, 1000, 1001]:
            for in_shape in [(n_seqs, 4, 1, 1, seq_len), (n_seqs, 4, 1, seq_len), (n_seqs, seq_len, 4)]:
                for undef_seqlen_schema in [True, False]:
                    content = np.arange(n_seqs * seq_len * 4)
                    start = np.reshape(content, in_shape)
                    input_shape = start.shape[1:]
                    seq_dim = np.where(np.array(in_shape) == seq_len)[0][0]
                    if undef_seqlen_schema:
                        input_shape = tuple([el if el != seq_len else None for el in list(input_shape)])
                    reshaper_obj = kipoi_veff.utils.generic.ReshapeDna(input_shape)
                    reshaped = reshaper_obj.to_standard(start)
                    reshaped_2 = reshaper_obj.from_standard(reshaped)
                    assert (np.all(start == reshaped_2))
                    assert (reshaped.shape[1:] == (seq_len, 4))
                    # check the transformed array:
                    one_hot_dim = np.where(np.array(in_shape) == 4)[0][0]
                    swap = seq_dim > one_hot_dim
                    # is the transformation performed correctly?
                    for n in range(n_seqs):
                        itm = np.squeeze(start[n, ...])
                        if swap:
                            itm = np.swapaxes(itm, 1, 0)
                        assert np.all(itm == reshaped[n, ...])
                    # make sure it fails if there is spmething wrong:
                    for expa in range(len(in_shape)):
                        with pytest.raises(Exception):
                            reshaped = reshaper_obj.to_standard(np.expand_dims(start, expa))
                    # check if it also works for a single sample with missing batch axis
                    with pytest.warns(None):
                        reshaped = reshaper_obj.to_standard(start[0, ...])
                        assert (reshaped.shape[1:] == (seq_len, 4))
                        reshaped_2 = reshaper_obj.from_standard(reshaped)
                        assert reshaped_2.shape == start.shape[1:]


def test_DNAStringArrayConverter():
    # there is a problem with shape (), also what is if there is only one sample and that's not properly in a batch?!
    in_shape = [(), (1,), (8,)]
    in_str = [np.array("ACGTAGCT"), np.array(["ACGTAGCT"]), np.array(list("ACGTAGCT"))]
    for shape, arr in zip(in_shape, in_str):
        for add_batch_axis in [True, False]:
            conv = kipoi_veff.utils.generic.ReshapeDnaString(shape)
            arr_here = copy.copy(arr)
            if add_batch_axis:
                arr_here = arr_here[None, ...]
            converted = conv.to_standard(arr_here)
            assert isinstance(converted, list)
            assert all([isinstance(el, str) for el in converted])
            arr_back = conv.from_standard(converted)
            assert np.all(arr_back == arr_here)
    # Any shape that has a length other than 0 or 1 is not allowed.
    with pytest.raises(Exception):
        conv = kipoi_veff.utils.generic.ReshapeDnaString((1, 8))


def test_search_vcf_in_regions(tmpdir):
    vcf_path = kipoi_veff.ensure_tabixed_vcf(temp("tests/models/rbp/example_files/variants.vcf", tmpdir))
    vcf_fh = cyvcf2.VCF(vcf_path, "r")
    ints1 = {"chr": ["chr22"] * 2, "start": [21541589, 30630701], "end": [21541953, 36702138], "strand": ["*"] * 2}
    ints2 = {"chr": ["chr22"] * 2, "start": [30630219, 30630220], "end": [30630222, 30630222], "strand": ["*"] * 2}
    model_input = {"metadata": {"gr_a": ints1, "gr_b": ints1, "gr_c": ints2}}
    seq_to_meta = {"seq_a": "gr_a", "seq_a2": "gr_a", "seq_b": "gr_b", "seq_c": "gr_c"}
    vcf_records, process_lines, process_seq_fields = kipoi_veff.snv_predict.get_variants_in_regions_search_vcf(
        model_input, seq_to_meta, vcf_fh)
    assert process_lines == [0, 0, 0, 1, 1]
    expected = [['seq_a2', 'seq_a', 'seq_b'], ['seq_a2', 'seq_a', 'seq_b'], ['seq_c'],
                ['seq_a2', 'seq_a', 'seq_b'], ['seq_a2', 'seq_a', 'seq_b']]
    assert all([set(el) == set(el2) for el, el2 in zip(process_seq_fields, expected)])
    for rec, l, field in zip(vcf_records, process_lines, process_seq_fields):
        for sid in field:
            ints = model_input["metadata"][seq_to_meta[sid]]
            assert (rec.POS >= ints["start"][l]) and (rec.POS <= ints["end"][l])


def test_merge_intervals():
    from kipoi_veff.snv_predict import merge_intervals
    ints1 = {"chr": ["chr1"], "start": [1234], "end": [2345], "strand": ["*"]}
    ints2 = {"chr": ["chr2"], "start": [1234], "end": [2345], "strand": ["*"]}
    ints3 = {"chr": ["chr1"], "start": [2345], "end": [2888], "strand": ["*"]}
    all_ints = {"a": ints1, "b": ints2, "c": ints3}
    merged_ints, ovlps = merge_intervals(all_ints)
    for i, labels in enumerate(ovlps):
        assert merged_ints["strand"][i] == "*"
        if merged_ints["chr"][i] == "chr1":
            assert merged_ints["start"][i] == 1234
            assert merged_ints["end"][i] == 2888
            assert labels == ["a", "c"]
        else:
            assert merged_ints["start"][i] == 1234
            assert merged_ints["end"][i] == 2345
            assert labels == ["b"]


def test_get_genomicranges_line():
    from kipoi_veff.snv_predict import get_genomicranges_line
    ints = {"chr": ["chr1", "chr2"], "start": [1234] * 2, "end": [2345] * 2, "strand": ["*"] * 2}
    for i in range(2):
        first_entry = get_genomicranges_line(ints, i)
        for k in ints:
            assert len(first_entry[k]) == 1
            assert first_entry[k][0] == ints[k][i]


def test_by_id_vcf_in_regions(tmpdir):
    from kipoi_veff.utils.generic import default_vcf_id_gen
    from kipoi_veff.snv_predict import get_variants_in_regions_sequential_vcf
    vcf_path = kipoi_veff.ensure_tabixed_vcf(temp("tests/models/rbp/example_files/variants.vcf", tmpdir))
    vcf_fh = cyvcf2.VCF(vcf_path, "r")
    ints1 = {"chr": [], "start": [], "end": [], "strand": [], "id": []}
    for rec in vcf_fh:
        ints1["chr"].append(rec.CHROM)
        ints1["start"].append(rec.POS - 20)
        ints1["end"].append(rec.POS + 20)
        ints1["strand"].append("*")
        ints1["id"].append(default_vcf_id_gen(rec))

    vcf_fh.close()
    vcf_fh = cyvcf2.VCF(vcf_path, "r")
    model_input = {"metadata": {"gr_a": ints1, "gr_b": ints1}}
    seq_to_meta = {"seq_a": "gr_a", "seq_a2": "gr_a", "seq_b": "gr_b"}
    vcf_records, process_lines, process_seq_fields, process_ids = get_variants_in_regions_sequential_vcf(model_input,
                                                                                                         seq_to_meta,
                                                                                                         vcf_fh,
                                                                                                         default_vcf_id_gen)
    num_entries = len(model_input["metadata"]["gr_a"]["chr"])
    assert len(vcf_records) == num_entries
    assert process_lines == list(range(num_entries))
    assert all([set(el) == set(seq_to_meta.keys()) for el in process_seq_fields])
    #
    # Now imitate bad id in one range:
    ints2 = copy.deepcopy(ints1)
    ints2["id"][2] = ""
    model_input = {"metadata": {"gr_a": ints1, "gr_b": ints2}}
    seq_to_meta = {"seq_a": "gr_a", "seq_a2": "gr_a", "seq_b": "gr_b"}
    with pytest.raises(Exception):
        get_variants_in_regions_sequential_vcf(model_input, seq_to_meta, vcf_fh, default_vcf_id_gen)


def test_get_preproc_conv(tmpdir):
    import itertools
    vcf_path = kipoi_veff.ensure_tabixed_vcf(temp("tests/models/rbp/example_files/variants.vcf", tmpdir))
    vcf_fh = cyvcf2.VCF(vcf_path, "r")
    ints1 = {"chr": ["chr22"] * 4, "start": [21541589, 30630701, 21541589, 200],
             "end": [21541953, 36702138, 21541953, 500], "strand": ["*"] * 4}
    ints2 = {"chr": ["chr22"] * 4, "start": [21541950, 30630220, 200, 200], "end": [30630220, 30630222, 500, 500],
             "strand": ["*"] * 4}
    model_input = {"metadata": {"gr_a": ints1, "gr_c": ints2}}
    seq_to_meta = {"seq_a": "gr_a", "seq_c": "gr_c"}
    vcf_records, process_lines, process_seq_fields = kipoi_veff.snv_predict.get_variants_in_regions_search_vcf(
        model_input,
        seq_to_meta,
        vcf_fh)
    process_ids = np.arange(len(process_lines))
    all_mut_seq_keys = list(set(itertools.chain.from_iterable(process_seq_fields)))

    assert (process_lines == [0, 0, 0, 1, 1, 2, 2])
    mut_seqs = {"seq_a": [0, 1, 3, 4, 5, 6], "seq_c": [1, 2]}
    # Start from the sequence inputs mentioned in the model.yaml
    for seq_key in all_mut_seq_keys:
        ranges_input_obj = model_input['metadata'][seq_to_meta[seq_key]]
        preproc_conv_df = kipoi_veff.snv_predict.get_variants_df(seq_key, ranges_input_obj,
                                                                 vcf_records,
                                                                 process_lines, process_ids,
                                                                 process_seq_fields)
        assert preproc_conv_df.query("do_mutate")["pp_line"].tolist() == mut_seqs[seq_key]
        assert preproc_conv_df.query("do_mutate").isnull().sum().sum() == 0


def test_DNAStringSequenceMutator():
    from kipoi_veff.utils.generic import DNAStringSequenceMutator, VariantLocalisation
    input_set = ["AGTGTCGT", "AGTGTCGT", "AGTGTCGT"]
    ref_mut_set = ["AGNGTCGT", "AGTGTCGT", "AGTGACGT"]
    preproc_conv = {"pp_line": [0, 1, 2], "varpos_rel": [2, 2, 3], "ref": ["T", "A", "A"],
                    "alt": ["N", "T", "T"],
                    "start": [0, 0, 0], "end": [7, 7, 7], "id": ["a", "b", "c"],
                    "do_mutate": [True, False, True],
                    "strand": ["+", "+", "-"]}
    #
    vl = VariantLocalisation()
    vl.data = preproc_conv
    mut_set = DNAStringSequenceMutator()(input_set, vl, "alt", "fwd")
    assert mut_set == ref_mut_set
    preproc_conv_bad = {"pp_line": [0, 1, 2], "varpos_rel": [2, 2, 3], "ref": ["T", "A", "G"],
                        "alt": ["N", "T", "A"],
                        "start": [0, 0, 0], "end": [7, 7, 7], "id": ["a", "b", "c"],
                        "do_mutate": [True, False, True],
                        "strand": ["+", "+", "-"]}
    #
    with pytest.warns(None):
        vl = VariantLocalisation()
        vl.data = preproc_conv_bad
        mut_set = DNAStringSequenceMutator()(input_set, vl, "ref", "fwd")
        ref_mut_set = ["AGTGTCGT", "AGTGTCGT", "AGTGCCGT"]
        assert mut_set == ref_mut_set


BASES = ['A', 'C', 'G', 'T']


def one_hot2string(arr):
    return "".join([['A', 'C', 'G', 'T', 'N'][x.argmax() if x.sum() != 0 else 4] for x in arr])


def onehot(seq):
    X = np.zeros((len(seq), len(BASES)))
    for i, char in enumerate(seq):
        X[i, BASES.index(char.upper())] = 1
    return X


def test_OneHotSequenceMutator():
    from kipoi_veff.utils.generic import OneHotSequenceMutator, VariantLocalisation
    input_set = ["AGTGTCGT", "AGTGTCGT", "AGTGTCGT"]
    ref_mut_set = ["AGNGTCGT", "AGTGTCGT", "AGTGACGT"]
    preproc_conv = {"pp_line": [0, 1, 2], "varpos_rel": [2, np.nan, 3], "ref": ["T", np.nan, "A"],
                    "alt": ["N", np.nan, "T"],
                    "start": [0, np.nan, 0], "end": [7, np.nan, 7], "id": ["a", "b", "c"],
                    "do_mutate": [True, False, True],
                    "strand": ["+", np.nan, "-"]}
    #
    input_set_onehot = np.array([onehot(el) for el in input_set])
    vl = VariantLocalisation()
    vl.data = preproc_conv
    mut_set_onehot = OneHotSequenceMutator()(input_set_onehot, vl, "alt", "fwd")
    mut_set = [one_hot2string(mut_set_onehot[i, ...]) for i in range(mut_set_onehot.shape[0])]
    assert mut_set == ref_mut_set
    preproc_conv_bad = {"pp_line": [0, 1, 2], "varpos_rel": [2, np.nan, 3], "ref": ["T", np.nan, "G"],
                        "alt": ["N", np.nan, "A"],
                        "start": [0, np.nan, 0], "end": [7, np.nan, 7], "id": ["a", "b", "c"],
                        "do_mutate": [True, False, True],
                        "strand": ["+", np.nan, "-"]}
    #
    with pytest.warns(None):
        vl.data = preproc_conv_bad
        input_set_onehot = np.array([onehot(el) for el in input_set])
        mut_set_onehot = OneHotSequenceMutator()(input_set_onehot, vl, "ref", "fwd")
        mut_set = [one_hot2string(mut_set_onehot[i, ...]) for i in range(mut_set_onehot.shape[0])]
        ref_mut_set = ["AGTGTCGT", "AGTGTCGT", "AGTGCCGT"]
        assert mut_set == ref_mut_set


def test_var_eff_pred_varseq(tmpdir):
    if sys.version_info[0] == 2:
        pytest.skip("rbp example not supported on python 2 ")
    model_dir = "tests/models/var_seqlen_model/"
    if INSTALL_REQ:
        install_model_requirements(model_dir, "dir", and_dataloaders=True)
    #
    model = kipoi.get_model(model_dir, source="dir")
    # The preprocessor
    Dataloader = kipoi.get_dataloader_factory(model_dir, source="dir")
    #
    dataloader_arguments = {
        "fasta_file": "example_files/hg38_chr22.fa",
        "preproc_transformer": "dataloader_files/encodeSplines.pkl",
        "gtf_file": "example_files/gencode_v25_chr22.gtf.pkl.gz",
        "intervals_file": "example_files/variant_centered_intervals.tsv"
    }
    dataloader_arguments = {k: model_dir + v for k, v in dataloader_arguments.items()}
    vcf_path = temp(model_dir + "example_files/variants.vcf", tmpdir)
    out_vcf_fpath = model_dir + "example_files/variants_generated.vcf"
    ref_out_vcf_fpath = model_dir + "example_files/variants_ref_out.vcf"
    #
    vcf_path = kipoi_veff.ensure_tabixed_vcf(vcf_path)
    model_info = kipoi_veff.ModelInfoExtractor(model, Dataloader)
    writer = kipoi_veff.VcfWriter(model, vcf_path, out_vcf_fpath, standardise_var_id=True)
    vcf_to_region = None
    with pytest.raises(Exception):
        # This has to raise an exception as the sequence length is None.
        vcf_to_region = kipoi_veff.SnvCenteredRg(model_info)
    res = sp.predict_snvs(model, Dataloader, vcf_path, dataloader_args=dataloader_arguments,
                          evaluation_function=analyse_model_preds, batch_size=32,
                          vcf_to_region=vcf_to_region,
                          evaluation_function_kwargs={'diff_types': {'diff': Diff("mean")}},
                          sync_pred_writer=writer)
    writer.close()
    # pass
    # assert filecmp.cmp(out_vcf_fpath, ref_out_vcf_fpath)
    compare_vcfs(out_vcf_fpath, ref_out_vcf_fpath)
    os.unlink(out_vcf_fpath)


def test_other_writers(tmpdir):
    if sys.version_info[0] == 2:
        pytest.skip("rbp example not supported on python 2 ")
    model_dir = "tests/models/var_seqlen_model/"
    if INSTALL_REQ:
        install_model_requirements(model_dir, "dir", and_dataloaders=True)
    #
    model = kipoi.get_model(model_dir, source="dir")
    # The preprocessor
    Dataloader = kipoi.get_dataloader_factory(model_dir, source="dir")
    #
    dataloader_arguments = {
        "fasta_file": "example_files/hg38_chr22.fa",
        "preproc_transformer": "dataloader_files/encodeSplines.pkl",
        "gtf_file": "example_files/gencode_v25_chr22.gtf.pkl.gz",
        "intervals_file": "example_files/variant_centered_intervals.tsv"
    }
    dataloader_arguments = {k: model_dir + v for k, v in dataloader_arguments.items()}
    vcf_path = model_dir + "example_files/variants.vcf"
    ref_out_vcf_fpath = model_dir + "example_files/variants_ref_out.vcf"
    #
    vcf_path = kipoi_veff.ensure_tabixed_vcf(vcf_path)
    model_info = kipoi_veff.ModelInfoExtractor(model, Dataloader)

    #
    from kipoi.writers import HDF5BatchWriter, TsvBatchWriter, MultipleBatchWriter

    h5_path = os.path.join(str(tmpdir), 'preds.h5')
    tsv_path = os.path.join(str(tmpdir), 'preds.tsv')
    writer = SyncBatchWriter(MultipleBatchWriter([HDF5BatchWriter(h5_path),
                                                  TsvBatchWriter(tsv_path)]))
    # writer = kipoi_veff.VcfWriter(model, vcf_path, out_vcf_fpath, standardise_var_id=True)

    vcf_to_region = None
    with pytest.raises(Exception):
        # This has to raise an exception as the sequence length is None.
        vcf_to_region = kipoi_veff.SnvCenteredRg(model_info)
    sp.predict_snvs(model, Dataloader, vcf_path, dataloader_args=dataloader_arguments,
                    evaluation_function=analyse_model_preds, batch_size=32,
                    vcf_to_region=vcf_to_region,
                    evaluation_function_kwargs={'diff_types': {'diff': Diff("mean")}},
                    return_predictions=False,
                    sync_pred_writer=writer)

    from kipoi.readers import HDF5Reader
    r = HDF5Reader.load(h5_path)
    assert len(r['line_idx']) == 6
    from kipoi_veff.parsers import KipoiVCFParser
    o = list(KipoiVCFParser(ref_out_vcf_fpath))
    assert len(o) == 6
    df = pd.read_table(tsv_path)
    assert len(df) == 6


def test_var_eff_pred(tmpdir):
    if sys.version_info[0] == 2:
        pytest.skip("rbp example not supported on python 2 ")
    # Take the rbp model
    model_dir = "tests/models/rbp/"
    if INSTALL_REQ:
        install_model_requirements(model_dir, "dir", and_dataloaders=True)
    #
    model = kipoi.get_model(model_dir, source="dir")
    # The preprocessor
    Dataloader = kipoi.get_dataloader_factory(model_dir, source="dir")
    #
    dataloader_arguments = {
        "fasta_file": "example_files/hg38_chr22.fa",
        "preproc_transformer": "dataloader_files/encodeSplines.pkl",
        "gtf_file": "example_files/gencode_v25_chr22.gtf.pkl.gz",
    }
    dataloader_arguments = {k: model_dir + v for k, v in dataloader_arguments.items()}
    #
    # Run the actual predictions
    vcf_path = temp(model_dir + "example_files/variants.vcf", tmpdir)
    out_vcf_fpath = model_dir + "example_files/variants_generated.vcf"
    ref_out_vcf_fpath = model_dir + "example_files/variants_ref_out.vcf"
    #
    # with cd(model.source_dir):
    model_info = kipoi_veff.ModelInfoExtractor(model, Dataloader)
    writer = kipoi_veff.VcfWriter(model, vcf_path, out_vcf_fpath,
                                  standardise_var_id=True)
    vcf_to_region = kipoi_veff.SnvCenteredRg(model_info)
    res = sp.predict_snvs(model, Dataloader, vcf_path, dataloader_args=dataloader_arguments,
                          evaluation_function=analyse_model_preds, batch_size=32,
                          vcf_to_region=vcf_to_region,
                          evaluation_function_kwargs={'diff_types': {'diff': Diff("mean")}},
                          sync_pred_writer=writer)
    writer.close()
    # with cd(model.source_dir):
    # pass
    # assert filecmp.cmp(out_vcf_fpath, ref_out_vcf_fpath)
    compare_vcfs(out_vcf_fpath, ref_out_vcf_fpath)
    os.unlink(out_vcf_fpath)


def test_var_eff_pred2(tmpdir):
    if sys.version_info[0] == 2:
        pytest.skip("rbp example not supported on python 2 ")
    # Take the rbp model
    model_dir = "tests/models/rbp/"
    if INSTALL_REQ:
        install_model_requirements(model_dir, "dir", and_dataloaders=True)
    #
    model = kipoi.get_model(model_dir, source="dir")
    # The preprocessor
    Dataloader = kipoi.get_dataloader_factory(model_dir, source="dir")
    #
    dataloader_arguments = {
        "fasta_file": "example_files/hg38_chr22.fa",
        "preproc_transformer": "dataloader_files/encodeSplines.pkl",
        "gtf_file": "example_files/gencode_v25_chr22.gtf.pkl.gz",
    }
    dataloader_arguments = {k: model_dir + v for k, v in dataloader_arguments.items()}
    #
    # Run the actual predictions
    vcf_path = temp(model_dir + "example_files/variants.vcf", tmpdir)
    out_vcf_fpath = model_dir + "example_files/variants_generated2.vcf"
    ref_out_vcf_fpath = model_dir + "example_files/variants_ref_out2.vcf"
    restricted_regions_fpath = model_dir + "example_files/restricted_regions.bed"
    #
    # with cd(model.source_dir):
    pbd = pb.BedTool(restricted_regions_fpath)
    model_info = kipoi_veff.ModelInfoExtractor(model, Dataloader)
    vcf_to_region = kipoi_veff.SnvPosRestrictedRg(model_info, pbd)
    writer = kipoi_veff.utils.io.VcfWriter(model, vcf_path, out_vcf_fpath,
                                           standardise_var_id=True)
    res = sp.predict_snvs(model, Dataloader, vcf_path, dataloader_args=dataloader_arguments,
                          evaluation_function=analyse_model_preds, batch_size=32,
                          vcf_to_region=vcf_to_region,
                          evaluation_function_kwargs={'diff_types': {'diff': Diff("mean")}},
                          sync_pred_writer=writer)
    writer.close()
    # with cd(model.source_dir):
    # pass
    # assert filecmp.cmp(out_vcf_fpath, ref_out_vcf_fpath)
    compare_vcfs(out_vcf_fpath, ref_out_vcf_fpath)
    os.unlink(out_vcf_fpath)


def test_Rc_merging():
    # test the variant effect calculation routines
    # test the different functions:
    arr_a = np.array([[1, 2], [3, 4]])
    arr_b = np.array([[2, 1], [5, 3]])
    for k in ["min", "max", "mean", "median", lambda x, y: x - y]:
        ro = RCScore(k)
        if k == "min":
            assert np.all(ro.rc_merging(arr_a, arr_b) == np.min([arr_a, arr_b], axis=0))
        elif k == "max":
            assert np.all(ro.rc_merging(arr_a, arr_b) == np.max([arr_a, arr_b], axis=0))
        elif k == "mean":
            assert np.all(ro.rc_merging(arr_a, arr_b) == np.mean([arr_a, arr_b], axis=0))
        elif k == "median":
            assert np.all(ro.rc_merging(arr_a, arr_b) == np.median([arr_a, arr_b], axis=0))
        else:
            assert np.all(ro.rc_merging(arr_a, arr_b) == arr_a - arr_b)
    assert np.all(
        RCScore.absmax(arr_a, arr_b * (-1), inplace=False) == np.array([[-2, 2], [-5, 4]]))
    x = RCScore.absmax(arr_a, arr_b * (-1), inplace=True)
    assert np.all(arr_a == np.array([[-2, 2], [-5, 4]]))


def test_enhanced_analysis_effects():
    probs_r = np.array([0.1, 0.2, 0.3])
    probs_a = np.array([0.2, 0.29, 0.9])
    counts = np.array([10, 23, -2])
    preds_prob = {"ref": probs_a, "ref_rc": probs_r, "alt": probs_a, "alt_rc": probs_a}
    preds_arb = {"ref": probs_a, "ref_rc": probs_r, "alt": counts, "alt_rc": counts}
    assert np.all((Logit("max")(**preds_prob) == logit(probs_a) - logit(probs_r)))
    assert np.all((Diff("max")(**preds_prob) == probs_a - probs_r))
    assert np.all(
        DeepSEA_effect("max")(**preds_prob) == np.abs(logit(probs_a) - logit(probs_r)) * np.abs(probs_a - probs_r))
    # now with values that contain values outside [0,1].
    with pytest.warns(UserWarning):
        x = (Logit()(**preds_arb))
    #
    with pytest.warns(UserWarning):
        x = (DeepSEA_effect()(**preds_arb))
    #
    assert np.all((Diff("max")(**preds_arb) == counts - probs_r))
    #
    preds_prob_r = {"ref": probs_r, "ref_rc": probs_r, "alt": probs_a, "alt_rc": probs_a}
    assert np.all((LogitAlt("max")(**preds_prob_r) == logit(probs_a)))
    assert np.all((LogitRef("max")(**preds_prob_r) == logit(probs_r)))


def test_output_reshaper():
    for k1 in RES:
        for k2 in YAMLS:
            if k1 == k2:
                o = OutputReshaper(ModelSchema.from_config(from_yaml(YAMLS[k2])).targets)
                fl, fll = o.flatten(RES[k1])
                assert (fl.shape[1] == RES_OUT_SHAPES[k1])
                assert (RES_OUT_LABELS[k2] == fll.tolist())
            elif (k1.replace("Lab", "NoLab") == k2) or (k1 == k2.replace("Lab", "NoLab")):
                o = OutputReshaper(ModelSchema.from_config(from_yaml(YAMLS[k2])).targets)
                fl, fll = o.flatten(RES[k1])
                assert (fl.shape[1] == RES_OUT_SHAPES[k1])
                assert (RES_OUT_LABELS[k2] == fll.tolist())
            else:
                with pytest.raises(Exception):
                    o = OutputReshaper(ModelSchema.from_config(from_yaml(YAMLS[k2])).targets)
                    fl, fll = o.flatten(RES[k1])


class Dummy_internval:

    def __init__(self):
        self.storage = {"chrom": [], "start": [], "end": [], "id": []}

    def append_interval(self, **kwargs):
        for k in kwargs:
            self.storage[k].append(kwargs[k])


def _write_regions_from_vcf(vcf_iter, vcf_id_generator_fn, int_write_fn, region_generator):
    for record in vcf_iter:
        if not is_indel_wrapper(record):
            region = region_generator(record)
            id = vcf_id_generator_fn(record)
            for chrom, start, end in zip(region["chrom"], region["start"], region["end"]):
                int_write_fn(chrom=chrom, start=start, end=end, id=id)


def test__generate_pos_restricted_seqs(tmpdir):
    model_dir = "tests/models/rbp/"
    vcf_path = temp(model_dir + "example_files/variants.vcf", tmpdir)
    tuples = (([21541490, 21541591], [21541491, 21541591]),
              ([21541390, 21541891], [21541541, 21541641]),
              ([21541570, 21541891], [21541571, 21541671]))
    model_info_extractor = DummyModelInfo(101)
    for tpl in tuples:
        vcf_fh = cyvcf2.VCF(vcf_path, "r")
        qbf = pb.BedTool("chr22 %d %d" % tuple(tpl[0]), from_string=True)
        regions = Dummy_internval()
        # sp._generate_pos_restricted_seqs(vcf_fh, sp._default_vcf_id_gen, qbf, regions.append_interval, seq_length)
        region_generator = kipoi_veff.SnvPosRestrictedRg(model_info_extractor, qbf)
        _write_regions_from_vcf(vcf_fh, kipoi_veff.utils.generic.default_vcf_id_gen,
                                regions.append_interval, region_generator)
        vcf_fh.close()
        regions_df = pd.DataFrame(regions.storage)
        assert regions_df.shape[0] == 1
        assert np.all(regions_df[["start", "end"]].values == tpl[1])


def test_BedOverlappingRg():
    tuples = ([21541490, 21541591], [21541490, 21541592])
    model_info_extractor = DummyModelInfo(101)
    for i, tpl in enumerate(tuples):
        qbf = pb.BedTool("chr22 %d %d" % tuple(tpl), from_string=True)
        regions = Dummy_internval()
        # sp._generate_pos_restricted_seqs(vcf_fh, sp._default_vcf_id_gen, qbf, regions.append_interval, seq_length)
        region_generator = kipoi_veff.BedOverlappingRg(model_info_extractor)
        for entry in qbf:
            ret_regions = region_generator(entry)
            regions_df = pd.DataFrame(ret_regions)
            assert regions_df.shape[0] == i + 1
            assert all([col in regions_df.columns.tolist() for col in ["chrom", "start", "end"]])


def test__generate_snv_centered_seqs(tmpdir):
    model_dir = "tests/models/rbp/"
    vcf_path = temp(model_dir + "example_files/variants.vcf", tmpdir)
    model_info_extractor = DummyModelInfo(101)
    lct = 0
    hdr = None
    with open(vcf_path, "r") as ifh:
        for l in ifh:
            if not l.startswith("#"):
                els = l.split("\t")
                if (len(els[3]) == 1) and (len(els[4]) == 1) and (els[3] != b".") and (els[4] != b".") and \
                        (els[3] != ".") and (els[4] != "."):
                    lct += 1
            elif l[2] != "#":
                hdr = l.lstrip("#").rstrip().split("\t")
    #
    vcf_df = pd.read_csv(vcf_path, sep="\t", comment='#', header=None, usecols=range(len(hdr)))
    vcf_df.columns = hdr
    # Subset the VCF to SNVs:
    vcf_df = vcf_df.loc[(vcf_df["REF"].str.len() == 1) & (vcf_df["ALT"].str.len() == 1), :]
    vcf_df = vcf_df.loc[vcf_df[["REF", "ALT"]].isin([".", b"."]).sum(axis=1) == 0, :]
    #
    for seq_length in [100, 101]:
        vcf_fh = cyvcf2.VCF(vcf_path, "r")
        regions = Dummy_internval()
        model_info_extractor.seq_length = seq_length
        region_generator = kipoi_veff.utils.generic.SnvCenteredRg(model_info_extractor)
        _write_regions_from_vcf(vcf_fh, kipoi_veff.utils.generic.default_vcf_id_gen,
                                regions.append_interval, region_generator)
        vcf_fh.close()
        regions_df = pd.DataFrame(regions.storage)
        #
        # 1-based format?
        assert ((regions_df["end"] - regions_df["start"] + 1) == seq_length).all()
        assert (regions_df.shape[0] == lct)
        assert (regions_df["start"].values == vcf_df["POS"] - int(seq_length / 2) + 1).all()


def test__generate_seq_sets(tmpdir):
    model_dir = "tests/models/rbp/"
    vcf_sub_path = "example_files/variants.vcf"

    vcf_path = temp(model_dir + vcf_sub_path, tmpdir)
    vcf_path = kipoi_veff.ensure_tabixed_vcf(vcf_path)
    # for any given input type: list, dict and np.array return 4 identical sets, except for mutated bases on one position
    seq_len = 101
    model_info_extractor = DummyModelInfo(seq_len)
    for num_seqs in [1, 5]:
        empty_seq_input = np.zeros((num_seqs, seq_len, 4))
        empty_seq_input[:, :, 0] = 1  # All As
        empty_other_input = np.zeros((num_seqs, seq_len, 4)) - 10
        #
        relv_seq_keys = ["seq"]
        #
        vcf_fh = cyvcf2.VCF(vcf_path)
        regions = Dummy_internval()
        #
        model_info_extractor.seq_length = seq_len
        region_generator = kipoi_veff.utils.generic.SnvCenteredRg(model_info_extractor)
        _write_regions_from_vcf(vcf_fh, kipoi_veff.utils.generic.default_vcf_id_gen,
                                regions.append_interval, region_generator)
        #
        vcf_fh.close()
        annotated_regions = pd.DataFrame(regions.storage).iloc[:num_seqs, :]
        #
        gr_meta = {
            "ranges": GenomicRanges(annotated_regions["chrom"].values, annotated_regions["start"].values - 1,
                                    annotated_regions["end"].values,
                                    annotated_regions["id"].values)}
        #
        dict_meta = {
            "ranges": {"chr": annotated_regions["chrom"].values, "start": annotated_regions["start"].values - 1,
                       "end": annotated_regions["end"].values,
                       "id": annotated_regions["id"].values}}
        #
        meta_data_options = [gr_meta, dict_meta]
        #
        seq_to_mut = {"seq": kipoi_veff.utils.generic.OneHotSequenceMutator()}
        seq_to_meta = {"seq": "ranges"}
        #
        sample_counter = sp.SampleCounter()
        for meta_data in meta_data_options:
            for vcf_search_regions in [False, True]:
                # Test the dict case:
                dataloader = dummy_container()
                dataloader.output_schema = dummy_container()
                seq_container = dummy_container()
                seq_container.associated_metadata = ["ranges"]
                dataloader.output_schema.inputs = {"seq": seq_container, "other_input": None}
                inputs = {"seq": copy.deepcopy(empty_seq_input), "other_input": copy.deepcopy(empty_other_input)}
                inputs_2nd_copy = copy.deepcopy(inputs)
                #
                model_input = {"inputs": inputs, "metadata": meta_data}
                vcf_fh = cyvcf2.VCF(vcf_path, "r")
                # relv_seq_keys, dataloader, model_input, vcf_fh, vcf_id_generator_fn, array_trafo=None
                ssets = sp._generate_seq_sets(dataloader.output_schema, model_input, vcf_fh,
                                              vcf_id_generator_fn=kipoi_veff.utils.generic.default_vcf_id_gen,
                                              seq_to_mut=seq_to_mut,
                                              seq_to_meta=seq_to_meta, sample_counter=sample_counter,
                                              vcf_search_regions=vcf_search_regions)
                vcf_fh.close()
                req_cols = ['alt', 'ref_rc', 'ref', 'alt_rc']
                assert np.all(np.in1d(req_cols, list(ssets.keys())))
                for k in req_cols:
                    for k2 in inputs:
                        assert (k2 in ssets[k])
                        if k2 not in relv_seq_keys:
                            assert np.all(ssets[k][k2] == inputs_2nd_copy[k2])
                        else:
                            # Assuming modification of matrices works as desired - see its own unit test
                            # Assuming 1-hot coding with background as 0
                            if k.endswith("fwd"):
                                assert np.sum(ssets[k][k2] != inputs_2nd_copy[k2]) == 2 * num_seqs
                #
                for k in ["ref", "alt"]:
                    for k2 in relv_seq_keys:
                        assert np.all(ssets[k][k2] == ssets[k + "_rc"][k2][:, ::-1, ::-1])
        #
        #
        # ------ Now also test the bed-restricted prediction -------
        restricted_regions_fpath = "example_files/restricted_regions.bed"
        #
        pbd = pb.BedTool(model_dir + restricted_regions_fpath)
        vcf_fh = cyvcf2.VCF(vcf_path, "r")
        regions = Dummy_internval()
        region_generator = kipoi_veff.SnvPosRestrictedRg(model_info_extractor, pbd)
        _write_regions_from_vcf(vcf_fh, kipoi_veff.utils.generic.default_vcf_id_gen,
                                regions.append_interval, region_generator)
        # sp._generate_pos_restricted_seqs(vcf_fh, sp._default_vcf_id_gen, pbd, regions.append_interval, seq_len)
        vcf_fh.close()
        annotated_regions = pd.DataFrame(regions.storage).iloc[:num_seqs, :]
        #
        gr_meta = {
            "ranges": GenomicRanges(annotated_regions["chrom"].values, annotated_regions["start"].values - 1,
                                    annotated_regions["end"].values,
                                    annotated_regions["id"].values)}
        #
        dict_meta = {
            "ranges": {"chr": annotated_regions["chrom"].values, "start": annotated_regions["start"].values - 1,
                       "end": annotated_regions["end"].values,
                       "id": annotated_regions["id"].values}}
        #
        meta_data_options = [gr_meta, dict_meta]
        #
        n_qseq = annotated_regions.shape[0]
        for meta_data in meta_data_options:
            for vcf_search_regions in [False, True]:
                # Test the dict case:
                dataloader = dummy_container()
                dataloader.output_schema = dummy_container()
                seq_container = dummy_container()
                seq_container.associated_metadata = ["ranges"]
                dataloader.output_schema.inputs = {"seq": seq_container, "other_input": None}
                inputs = {"seq": copy.deepcopy(empty_seq_input[:n_qseq, ...]),
                          "other_input": copy.deepcopy(empty_other_input[:n_qseq, ...])}
                inputs_2nd_copy = copy.deepcopy(inputs)
                #
                model_input = {"inputs": inputs, "metadata": meta_data}
                vcf_fh = cyvcf2.VCF(vcf_path, "r")
                # relv_seq_keys, dataloader, model_input, vcf_fh, vcf_id_generator_fn, array_trafo=None
                sample_counter = sp.SampleCounter()
                ssets = sp._generate_seq_sets(dataloader.output_schema, model_input, vcf_fh,
                                              vcf_id_generator_fn=kipoi_veff.utils.generic.default_vcf_id_gen,
                                              seq_to_mut=seq_to_mut,
                                              seq_to_meta=seq_to_meta,
                                              sample_counter=sample_counter,
                                              vcf_search_regions=vcf_search_regions)
                vcf_fh.close()
                req_cols = ['alt', 'ref_rc', 'ref', 'alt_rc']
                assert np.all(np.in1d(req_cols, list(ssets.keys())))
                for k in req_cols:
                    for k2 in inputs:
                        assert (k2 in ssets[k])
                        if k2 not in relv_seq_keys:
                            assert np.all(ssets[k][k2] == inputs_2nd_copy[k2])
                        else:
                            # Assuming modification of matrices works as desired - see its own unit test
                            # Assuming 1-hot coding with background as 0
                            if k.endswith("fwd"):
                                assert np.sum(ssets[k][k2] != inputs_2nd_copy[k2]) == 2 * n_qseq
                #
                for k in ["ref", "alt"]:
                    for k2 in relv_seq_keys:
                        assert np.all(ssets[k][k2] == ssets[k + "_rc"][k2][:, ::-1, ::-1])
                #
                # Now also assert that the nuc change has been performed at the correct position:
                # Region: chr22 36702133    36706137
                # Variant within: chr22 36702137    rs1116  C   A   .   .   .
                mut_pos = 36702137 - 36702134  # bed file is 0-based
                assert np.all(ssets["ref"]["seq"][0, mut_pos, :] == np.array([0, 1, 0, 0]))
                assert np.all(ssets["alt"]["seq"][0, mut_pos, :] == np.array([1, 0, 0, 0]))


def test_subsetting():
    for sel in [[0], [1, 2, 3]]:
        for k in RES:
            if "dict" in k:
                ret = sp.select_from_dl_batch(RES[k], sel, 50)
                for k2 in ret:
                    assert ret[k2].shape[0] == len(sel)
                with pytest.raises(Exception):
                    ret = sp.select_from_dl_batch(RES[k], sel, 20)
            elif "list" in k:
                ret = sp.select_from_dl_batch(RES[k], sel, 50)
                assert all([el.shape[0] == len(sel) for el in ret])
                with pytest.raises(Exception):
                    ret = sp.select_from_dl_batch(RES[k], sel, 20)
            else:
                ret = sp.select_from_dl_batch(RES[k], sel, 50)
                assert ret.shape[0] == len(sel)
                with pytest.raises(Exception):
                    ret = sp.select_from_dl_batch(RES[k], sel, 20)


def test_ensure_tabixed_vcf(tmpdir):
    vcf_in_fpath = temp("tests/models/rbp/example_files/variants.vcf", tmpdir)
    vcf_path = kipoi_veff.ensure_tabixed_vcf(vcf_in_fpath)
    assert os.path.exists(vcf_path)
    assert vcf_path.endswith(".gz")
    with pytest.raises(Exception):
        # since the file exists, we should now complain
        vcf_path = kipoi_veff.ensure_tabixed_vcf(vcf_in_fpath, force_tabix=False)
    vcf_in_fpath_gz = vcf_in_fpath + ".gz"
    assert vcf_in_fpath_gz == kipoi_veff.ensure_tabixed_vcf(vcf_in_fpath_gz)


def test__overlap_vcf_region(tmpdir):
    vcf_path = kipoi_veff.ensure_tabixed_vcf(temp("tests/models/rbp/example_files/variants.vcf", tmpdir))
    vcf_obj = cyvcf2.VCF(vcf_path)
    all_records = [rec for rec in vcf_obj]
    vcf_obj.close()
    vcf_obj = cyvcf2.VCF(vcf_path)
    #
    regions_dict = {"chr": ["chr22"], "start": [21541589], "end": [36702137], "id": [0]}
    regions_gr = GenomicRanges(regions_dict["chr"], regions_dict["start"],
                               regions_dict["end"], regions_dict["id"])
    for regions in [regions_dict, regions_gr]:
        found_vars, overlapping_region = sp._overlap_vcf_region(vcf_obj, regions, exclude_indels=False)
        assert all([str(el1) == str(el2) for el1, el2 in zip(all_records, found_vars)])
        assert len(overlapping_region) == len(found_vars)
        assert all([el == 0 for el in overlapping_region])

    regions_dict = {"chr": ["chr22", "chr22", "chr22"], "start": [21541589, 21541589, 30630220],
                    "end": [36702137, 21541590, 30630222], "id": [0, 1, 2]}
    regions_gr = GenomicRanges(regions_dict["chr"], regions_dict["start"],
                               regions_dict["end"], regions_dict["id"])
    #
    plus_indel_results = all_records + all_records[:1] + all_records[3:4]
    snv_results = [el for el in plus_indel_results if not is_indel_wrapper(el)]
    #
    ref_lines_indel = [0] * len(all_records) + [1] + [2]
    snv_ref_lines = [el for el, el1 in zip(ref_lines_indel, plus_indel_results) if not is_indel_wrapper(el1)]
    #
    for regions in [regions_dict, regions_gr]:
        for exclude_indels, ref_res, ref_lines in zip([False, True], [plus_indel_results, snv_results],
                                                      [ref_lines_indel, snv_ref_lines]):
            found_vars, overlapping_region = sp._overlap_vcf_region(vcf_obj, regions, exclude_indels)
            assert all([str(el1) == str(el2) for el1, el2 in zip(ref_res, found_vars) if not is_indel_wrapper(el1)])
            assert overlapping_region == ref_lines


"""
# Take the rbp model
model_dir = "tests/models/rbp/"
install_model_requirements(model_dir, "dir", and_dataloaders=True)

model = kipoi.get_model(model_dir, source="dir")
# The preprocessor
Dataloader = kipoi.get_dataloader_factory(model_dir, source="dir")

dataloader_arguments = {
    "fasta_file": "example_files/hg38_chr22.fa",
    "preproc_transformer": "dataloader_files/encodeSplines.pkl",
    "gtf_file": "example_files/gencode_v25_chr22.gtf.pkl.gz",
}

# Run the actual predictions
vcf_path = "example_files/variants.vcf"
out_vcf_fpath = "example_files/variants_generated.vcf"
ref_out_vcf_fpath = "example_files/variants_ref_out.vcf"


with cd(model.source_dir):
    res = ve.predict_snvs(model, vcf_path, dataloader_args=dataloader_arguments,
                          evaluation_function=analyse_model_preds,
                       dataloader=Dataloader, batch_size=32,
                       evaluation_function_kwargs={'diff_types':{'diff':Diff("absmax")}},
                       out_vcf_fpath=out_vcf_fpath)
    assert filecmp.cmp(out_vcf_fpath, ref_out_vcf_fpath)
    os.unlink(out_vcf_fpath)
"""


def test_rc_str():
    input = "ACTGGN"
    output = "NCCAGT"
    assert rc_str(input) == output
    assert rc_str(input.lower()) == output.lower()


def test_modify_single_string_base():
    input = "ACTGG"
    pos = 3
    allele = "N"
    ret = "ACTNG"
    assert _modify_single_string_base(input, pos, allele, False) == ret
    assert _modify_single_string_base(rc_str(input), pos, allele, True) == rc_str(ret)


def test_all_scoring_options_available():
    from kipoi_veff.specs import VarEffectFuncType

    assert {x.value for x in list(VarEffectFuncType)} == \
        set(list(scoring_options.keys()) + ["custom"])


def test_homogenise_seqname():
    possible_seqnames_pref = ["chr22", "chr22", "chr21"]
    possible_seqnames_bad = ["chr22", "22", "chr21"]
    possible_seqnames = ["21", "22"]
    assert "chr22" == homogenise_seqname("22", possible_seqnames_pref)
    assert "chr22" == homogenise_seqname("chr22", possible_seqnames_pref)
    assert "22" == homogenise_seqname("22", possible_seqnames)
    assert "22" == homogenise_seqname("chr22", possible_seqnames)
    homogenise_seqname("22", possible_seqnames_bad)
    with pytest.raises(Exception):
        homogenise_seqname("21", possible_seqnames_bad)


def test_get_vcf_to_region():
    if sys.version_info[0] == 2:
        pytest.skip("rbp example not supported on python 2 ")
    from kipoi_veff import ModelInfoExtractor, SnvCenteredRg, SnvPosRestrictedRg
    from kipoi_veff.snv_predict import _get_vcf_to_region
    example_dir = "tests/models/rbp"
    model = kipoi.get_model(example_dir, source="dir")
    restr_bed = example_dir + "/example_files/restricted_regions.bed"
    dataloader = model.default_dataloader
    model_info = ModelInfoExtractor(model, dataloader)
    assert isinstance(_get_vcf_to_region(model_info, None, None), SnvCenteredRg)
    assert isinstance(_get_vcf_to_region(model_info, restr_bed, None), SnvPosRestrictedRg)

    example_dir = "tests/models/non_bedinput_model"
    model = kipoi.get_model(example_dir, source="dir")
    dataloader = model.default_dataloader
    model_info = ModelInfoExtractor(model, dataloader)
    assert _get_vcf_to_region(model_info, None, None) is None


def test_score_variants(tmpdir):
    if sys.version_info[0] == 2:
        pytest.skip("rbp example not supported on python 2 ")
    # Take the rbp model
    model_dir = "tests/models/rbp/"
    if INSTALL_REQ:
        install_model_requirements(model_dir, "dir", and_dataloaders=True)
    #
    model = kipoi.get_model(model_dir, source="dir")
    #
    dataloader_arguments = {
        "fasta_file": "example_files/hg38_chr22.fa",
        "preproc_transformer": "dataloader_files/encodeSplines.pkl",
        "gtf_file": "example_files/gencode_v25_chr22.gtf.pkl.gz",
    }
    dataloader_arguments = {k: model_dir + v for k, v in dataloader_arguments.items()}
    #
    # Run the actual predictions
    vcf_path = model_dir + "example_files/variants.vcf"
    out_vcf_fpath = os.path.join(str(tmpdir), "variants_generated.vcf")
    out_vcf_fpath2 = os.path.join(str(tmpdir), "variants_generated2.vcf")
    ref_out_vcf_fpath = model_dir + "example_files/variants_ref_out.vcf"

    # with cd(model.source_dir):
    res = sp.score_variants(model, dataloader_arguments, vcf_path, out_vcf_fpath,
                            scores=['diff'], score_kwargs=[{"rc_merging": "mean"}], source="dir",
                            model_outputs=['rbp_prb'])

    res = sp.score_variants(model, dataloader_arguments, vcf_path, out_vcf_fpath2,
                            scores=['diff'], score_kwargs=[{"rc_merging": "mean"}], source="dir",
                            model_outputs=[True], return_predictions=True)

    # pass
    #assert filecmp.cmp(out_vcf_fpath, ref_out_vcf_fpath)
    compare_vcfs(out_vcf_fpath, ref_out_vcf_fpath)
    os.unlink(out_vcf_fpath)

    res = sp.score_variants(model.source_dir, dataloader_arguments, vcf_path, out_vcf_fpath,
                            scores=['diff'], score_kwargs=[{"rc_merging": "mean"}], source="dir")

    # pass
    #assert filecmp.cmp(out_vcf_fpath, ref_out_vcf_fpath)
    assert os.path.exists(out_vcf_fpath)
    os.unlink(out_vcf_fpath)


def test_score_variant_subsetting(tmpdir):
    from kipoi.utils import cd

    if INSTALL_REQ:
        install_model_requirements("DeepSEA/variantEffects", source="kipoi", and_dataloaders=True)
    model = kipoi.get_model("DeepSEA/variantEffects", source="kipoi")
    #
    import os
    cwd = os.getcwd()
    dataloader_arguments = {"fasta_file": cwd + "/tests/data/hg38_chr22.fa"}
    #
    model_output_names = model.schema.targets.column_labels
    # Run the actual predictions
    vcf_path = os.path.realpath(temp("tests/models/rbp/example_files/variants.vcf", tmpdir))
    out_vcf_fpath = vcf_path[:-4] + "_DS.vcf"

    for sel_idxs in [[3], [3, 4, 10]]:
        bool_idx = np.in1d(np.arange(len(model_output_names)), sel_idxs)
        str_idx = [model_output_names[sel_idx] for sel_idx in sel_idxs]
        for idx in [sel_idxs, bool_idx, str_idx]:
            with cd(model.source_dir):
                idx_here = idx
                if len(idx) == 1:
                    idx_here = idx_here[0]
                res = sp.score_variants(model, dataloader_arguments, vcf_path, out_vcf_fpath,
                                        scores=['diff'], score_kwargs=[{"rc_merging": "mean"}], source="dir",
                                        model_outputs=idx_here,
                                        return_predictions=True)
                assert set(res['diff'].columns) == set(str_idx)
