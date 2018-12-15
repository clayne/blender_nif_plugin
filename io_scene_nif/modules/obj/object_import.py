"""This script contains helper methods to import objects."""

# ***** BEGIN LICENSE BLOCK *****
# 
# Copyright © 2005-2015, NIF File Format Library and Tools contributors.
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
# 
#    * Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials provided
#      with the distribution.
# 
#    * Neither the name of the NIF File Format Library and Tools
#      project nor the names of its contributors may be used to endorse
#      or promote products derived from this software without specific
#      prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# ***** END LICENSE BLOCK *****
from functools import singledispatch

import bpy

from pyffi.formats.nif import NifFormat

from io_scene_nif.modules import armature, obj
from io_scene_nif.utility.nif_global import NifOp
from io_scene_nif.utility.nif_logging import NifLog


def import_name(n_block, max_length=63):
    """Get unique name for an object, preserving existing names.
    The maximum name length defaults to 63, since this is the
    maximum for Blender objects.

    :param n_block: A named nif block.
    :type n_block: :class:`~pyffi.formats.nif.NifFormat.NiObjectNET`
    :param max_length: The maximum length of the name.
    :type max_length: :class:`int`
    """
    if n_block is None:
        return None

    if n_block in obj.DICT_NAMES:
        return obj.DICT_NAMES[n_block]

    NifLog.debug("Importing name for {0} block from {1}".format(n_block.__class__.__name__, n_block.name))

    # find unique name for Blender to use
    n_name = n_block.name.decode()
    # if name is empty, create something non-empty
    if not n_name:
        if isinstance(n_block, NifFormat.RootCollisionNode):
            n_name = "RootCollisionNode"
        else:
            n_name = "noname"

    for uniqueInt in range(-1, 1000):
        # limit name length
        if uniqueInt == -1:
            short_name = n_name[:max_length - 1]
        else:
            short_name = ('%s.%02d' % (n_name[:max_length - 4], uniqueInt))
        # bone naming convention for blender
        short_name = armature.get_bone_name_for_blender(short_name)
        # make sure it is unique
        if n_name == "InvMarker":
            if n_name not in obj.DICT_NAMES:
                break
        if (short_name not in bpy.data.objects
                and short_name not in bpy.data.materials
                and short_name not in bpy.data.meshes):
            # shortName not in use anywhere
            break
    else:
        raise RuntimeError("Ran out of names.")
    # save mapping

    # block niBlock has Blender name shortName
    obj.DICT_NAMES[n_block] = short_name

    # Blender name shortName corresponds to niBlock
    armature.DICT_BLOCKS[short_name] = n_block
    NifLog.debug("Selected unique name {0}".format(short_name))
    return short_name


class ObjectProperty:

    def __init__(self):
        self.n_block = None
        self.b_obj = None
        self.process_data = singledispatch(self.process_extra_data)
        self.process_data.register(NifFormat.BSXFlags, self.process_bsx_flag_data)
        self.process_data.register(NifFormat.BSBound, self.process_bsbound_data)
        self.process_data.register(NifFormat.NiStringExtraData, self.process_nistring_data)

    def process_data_list(self, n_block, b_obj):
        self.n_block = n_block
        self.b_obj = b_obj
        for n_extra in n_block.get_extra_datas():
            NifLog.debug("About to process" + str(type(n_extra)))
            self.process_data(n_extra)
        return

    def process_extra_data(self, n_extra):
        """Base method to warn user that this property is not supported"""
        NifLog.warn("Unknown property block found: " + str(n_extra))
        NifLog.warn("This type isn't currently supported: {}".format(type(n_extra)))

    def process_nistring_data(self, n_extra):
        """Process NiStringExtraData based blocks"""
        # TODO [properties] [object] Store extra data
        NifLog.debug("Extra Data: Processing String data - " + str(n_extra))

        if n_extra.name.decode() == "UPB":
            upbflags = n_extra.string_data.decode()
            return upbflags

    def process_bsx_flag_data(self, n_extra):
        """Process BSBound nodea based blocks"""
        NifLog.debug("Extra Data: Processing BSX Flag data")
        # TODO [properties] [object] Store extra data
        bsxflags = n_extra.integer_data
        return bsxflags

    def process_bsbound_data(self, n_extra):
        """Process BSBound nodea based blocks"""
        NifLog.debug("Extra Data: Processing BSBound")
        self.boundhelper.import_bounding_box(n_extra)


class NiObject:
    pass
    # TODO [object] [properties]
    # self.bsx_flags = self.objecthelper.import_bsxflag_data(root_block)
    # self.upb_flags = self.objecthelper.import_upbflag_data(root_block)
    # self.object_flags = root_block.flags
    #
    # if isinstance(root_block, NifFormat.BSFadeNode):
    #     self.root_ninode = 'BSFadeNode'

    # TODO [Object] process at object level
    # process extra_data_list
    # if hasattr(root_block, "extra_data_list"):
    #     for n_extra_list in root_block.extra_data_list:
    #         if isinstance(n_extra_list, NifFormat.BSInvMarker):
    #             b_obj.niftools_bs_invmarker.add()
    #             b_obj.niftools_bs_invmarker[0].name = n_extra_list.name.decode()
    #             b_obj.niftools_bs_invmarker[0].bs_inv_x = n_extra_list.rotation_x
    #             b_obj.niftools_bs_invmarker[0].bs_inv_y = n_extra_list.rotation_y
    #             b_obj.niftools_bs_invmarker[0].bs_inv_z = n_extra_list.rotation_z
    #             b_obj.niftools_bs_invmarker[0].bs_inv_zoom = n_extra_list.zoom
    #
    # if self.root_ninode:
    #     b_obj.niftools.rootnode = self.root_ninode


class Empty:

    def import_empty(self, n_block):
        """Creates and returns a grouping empty."""
        shortname = import_name(n_block)
        b_empty = bpy.data.objects.new(shortname, None)

        # TODO [object] - is longname needed??? Yes it is needed, it resets the original name on export
        b_empty.niftools.longname = n_block.name.decode()

        bpy.context.scene.objects.link(b_empty)
        ObjectProperty().process_data_list(n_block, b_empty)

        # TODO [object][properties]
        # b_empty.niftools.bsxflags = NiObject.import_bsxflag_data(n_block)
        # b_empty.niftools.objectflags = n_block.flags

        # TODO [armature]
        # if niBlock.name in armature.DICT_BONE_PRIORITIES:
        #     constr = b_empty.constraints.append(bpy.types.Constraint.NULL)
        #     constr.name = "priority:%i" % armature.DICT_BONE_PRIORITIES[niBlock.name]
        return b_empty


def is_grouping_node(n_block):
    """Determine whether node is grouping node.
    Returns the children which are grouped, or empty list if it is not a
    grouping node.
    """
    # combining shapes: disable grouping
    if not NifOp.props.combine_shapes:
        return []
    # check that it is a ninode
    if not isinstance(n_block, NifFormat.NiNode):
        return []
    # NiLODNodes are never grouping nodes
    # (this ensures that they are imported as empties, with LODs
    # as child meshes)
    if isinstance(n_block, NifFormat.NiLODNode):
        return []
    # root collision node: join everything
    if isinstance(n_block, NifFormat.RootCollisionNode):
        return [child for child in n_block.children if
                isinstance(child, NifFormat.NiTriBasedGeom)]
    # check that node has name
    node_name = n_block.name
    if not node_name:
        return []
    # strip "NonAccum" trailer, if present
    if node_name[-9:].lower() == " nonaccum":
        node_name = node_name[:-9]
    # get all geometry children
    return [child for child in n_block.children if (isinstance(child, NifFormat.NiTriBasedGeom) and child.name.find(node_name) != -1)]
