from related import from_yaml
import pytest

from kipoi_veff.specs import VarEffectModelArgs
from kipoi_veff.scores import builtin_default_kwargs
from kipoi_veff.scores import get_avail_scoring_fns, get_scoring_fns
from kipoi_veff.scores import Diff, Ref, LogitRef, Alt, Logit, LogitAlt, DeepSEA_effect


class dummy_container(object):
    pass


def assert_groupwise_identity(group_a, group_b, equality_test=lambda x, y: x == y):
    # Function that asserts that the elements, ordered by the first group list, are identical
    # First element in group-wise identity tests have to be unique!
    if (len(list(set(group_a[0]))) != len(group_a[0])) or (len(list(set(group_b[0]))) != len(group_b[0])):
        raise Exception("First list entries have to contain unique values for both groups!")
    ref_index = None
    for a, b in zip(group_a, group_b):
        if ref_index is None:
            ref_index = [b.index(el_a) for el_a in a]
        else:
            assert all([equality_test(b[i], el_a) for i, el_a in zip(ref_index, a)])


postproc_yaml = """
seq_input:
  - seq
scoring_functions:%s
  - type: logit
  - type: deepsea_effect
    default: True
  - name: mydiff
    type: custom
    defined_as: tests/data/dummy_diff.py::LogitAlt
%s
"""

dupl_name_postproc_yaml = """
seq_input:
  - seq
scoring_functions:%s
  - type: deepsea_effect
    default: True
    name: mydiff
  - name: mydiff
    type: custom
    defined_as: tests/data/dummy_diff.py::LogitAlt
%s
"""

diff_str = """
  - name: diff
    type: diff
"""

args_w_default = """    args:
      rc_merging:
        default: "max"
"""

optional_args = """    args:
      rc_merging:
        optional: true
"""


def test_custom_fns():
    template_avail_scoring_fns = [Logit, DeepSEA_effect, LogitAlt]
    template_avail_scoring_fn_labels = ["logit", "deepsea_effect", "mydiff"]
    #
    exp_avail_scoring_fns = [template_avail_scoring_fns + [Diff] + [Ref, Alt, LogitRef],
                             [Diff] + template_avail_scoring_fns + [Ref, Alt, LogitRef]]
    exp_avail_scoring_fn_labels = [template_avail_scoring_fn_labels + ["diff"] + ["ref", "alt", "logit_ref"],
                                   ["diff"] + template_avail_scoring_fn_labels + ["ref", "alt", "logit_ref"]]
    #
    for i, diff_str_here in enumerate(["", diff_str]):
        if diff_str_here == "":
            exp_avail_scoring_fn_def_args = [None, [builtin_default_kwargs] * 2 +
                                             [{"rc_merging": "max"}] + [builtin_default_kwargs] * 4,
                                             [builtin_default_kwargs] * 2 + [{}] + [builtin_default_kwargs] * 5]
        else:
            exp_avail_scoring_fn_def_args = [None, [builtin_default_kwargs] * 3 +
                                             [{"rc_merging": "max"}] + [builtin_default_kwargs] * 4,
                                             [builtin_default_kwargs] * 3 + [{}] + [builtin_default_kwargs] * 5]
        for i2, mydiff_args in enumerate(["", args_w_default, optional_args]):
            for i3, pp_yaml in enumerate([postproc_yaml, dupl_name_postproc_yaml]):
                pps = VarEffectModelArgs.from_config(from_yaml(pp_yaml % (diff_str_here, mydiff_args)))
                model = dummy_container()
                model.postprocessing = {"variant_effects": pps}
                if i3 == 1:
                    with pytest.raises(Exception):
                        get_avail_scoring_fns(model)
                else:
                    if i2 == 0:
                        # mydiff has one argument but none are defined.
                        with pytest.raises(ValueError):
                            get_avail_scoring_fns(model)
                    else:
                        avail_scoring_fns, avail_scoring_fn_def_args, avail_scoring_fn_names, default_scoring_fns =\
                            get_avail_scoring_fns(model)
                        output = [avail_scoring_fn_names, avail_scoring_fns, avail_scoring_fn_def_args]
                        expected = [exp_avail_scoring_fn_labels[i], exp_avail_scoring_fns[i],
                                    exp_avail_scoring_fn_def_args[i2]]
                        assert_groupwise_identity(output, expected)
                        assert default_scoring_fns == ["deepsea_effect"]
    model = dummy_container()
    model.postprocessing = dummy_container()
    model.postprocessing = {}
    with pytest.raises(Exception):
        get_avail_scoring_fns(model)


def test_ret():
    pps = VarEffectModelArgs.from_config(from_yaml(postproc_yaml % ('', args_w_default)))
    model = dummy_container()
    model.postprocessing = {"variant_effects": pps}
    avail_scoring_fns, avail_scoring_fn_def_args, avail_scoring_fn_names,\
        default_scoring_fns = get_avail_scoring_fns(model)


postproc_yaml_nofndef = """
seq_input:
  - seq
"""


# by default at least and only offer the diff functionality
def test_default_diff():
    pps = VarEffectModelArgs.from_config(from_yaml(postproc_yaml_nofndef))
    model = dummy_container()
    model.postprocessing = {"variant_effects": pps}
    avail_scoring_fns, avail_scoring_fn_def_args, avail_scoring_fn_names, default_scoring_fns =\
        get_avail_scoring_fns(model)
    #
    output = [avail_scoring_fn_names, avail_scoring_fns, avail_scoring_fn_def_args]
    expected = [["diff", "ref", "alt"], [Diff, Ref, Alt], [builtin_default_kwargs] * 3]
    assert_groupwise_identity(output, expected)
    assert default_scoring_fns == ["diff"]


# test duplication of names
dupl_name_yaml = """
seq_input:
  - seq
scoring_functions:
  - type: logit
    name: logit
  - type: logit
    name: logit
"""


def test_dupl_name():
    pps = VarEffectModelArgs.from_config(from_yaml(dupl_name_yaml))
    model = dummy_container()
    model.postprocessing = {"variant_efffects": pps}
    with pytest.raises(Exception):
        get_avail_scoring_fns(model)


# test modification of name with custom_
rename_custom_yaml = """
seq_input:
  - seq
scoring_functions:
  - name: logit
    type: custom
    defined_as: tests/data/dummy_diff.py::LogitAlt
    args:
      rc_merging:
        default: "max"
"""


def test_rename_custom():
    pps = VarEffectModelArgs.from_config(from_yaml(rename_custom_yaml))
    model = dummy_container()
    model.postprocessing = {"variant_effects": pps}
    avail_scoring_fns, avail_scoring_fn_def_args, avail_scoring_fn_names, default_scoring_fns =\
        get_avail_scoring_fns(model)
    output = [avail_scoring_fn_names]
    expected = [["custom_logit", "diff", "ref", "alt", "logit_ref", "logit", "deepsea_effect"]]
    assert_groupwise_identity(output, expected)
    assert default_scoring_fns == ["custom_logit"]


postproc_autodefault_yaml = """
seq_input:
  - seq
scoring_functions:
  - type: logit
  - type: deepsea_effect
  - name: mydiff
    type: custom
    defined_as: tests/data/dummy_diff.py::LogitAlt
    args:
      rc_merging:
        default: "max"
"""


# if no default is set all scoring functions are used.
def test_auto_default():
    pps = VarEffectModelArgs.from_config(from_yaml(postproc_autodefault_yaml))
    model = dummy_container()
    model.postprocessing = {"variant_effects": pps}
    avail_scoring_fns, avail_scoring_fn_def_args, avail_scoring_fn_names, default_scoring_fns = \
        get_avail_scoring_fns(model)
    output = [avail_scoring_fn_names]
    expected = [default_scoring_fns + ["logit_ref", "diff", "ref", "alt"]]
    assert_groupwise_identity(output, expected)


postproc_cli_yaml = """
seq_input:
  - seq
scoring_functions:
  - type: logit
  - type: deepsea_effect
"""


def test__get_scoring_fns():
    pps = VarEffectModelArgs.from_config(from_yaml(postproc_cli_yaml))
    model = dummy_container()
    model.postprocessing = {"variant_effects": pps}
    scorers = [{"logit": Logit, "deepsea_effect": DeepSEA_effect}, {"logit": Logit}, {}]
    kwargs = {"rc_merging": 'max'}
    for sel_scoring_labels, scorer in zip([[], ["logit"], ["inexistent", "logit"], ["all"]], scorers):
        jk_list = [kwargs] * len(sel_scoring_labels)
        for sel_scoring_kwargs in [[], jk_list]:
            if "inexistent" in sel_scoring_labels:
                with pytest.warns(None):
                    dts = get_scoring_fns(model, sel_scoring_labels, sel_scoring_kwargs)
            else:
                dts = get_scoring_fns(model, sel_scoring_labels, sel_scoring_kwargs)
                for k in scorer:
                    assert isinstance(dts[k], scorer[k])
    with pytest.raises(Exception):
        get_scoring_fns(model, ["all"], [kwargs])
