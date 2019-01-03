"""This script contains classes to help import animations."""

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
import bpy

import mathutils

from pyffi.formats.nif import NifFormat

from io_scene_nif.modules.obj import blocks
from io_scene_nif.utility import nif_utils
from io_scene_nif.utility.nif_logging import NifLog
from io_scene_nif.utility.nif_global import NifOp
from io_scene_nif.modules import animation, armature


class AnimationHelper:

    def __init__(self):
        self.object_animation = ObjectAnimation()
        self.material_animation = MaterialAnimation()
        self.armature_animation = ArmatureAnimation()

    def import_kf_root(self, kf_root, root):
        """Merge kf into nif.

        *** Note: this function will eventually move to PyFFI. ***
        """

        NifLog.info("Merging kf tree into nif tree")

        # check that this is an Oblivion style kf file
        if not isinstance(kf_root, NifFormat.NiControllerSequence):
            raise nif_utils.NifError("non-Oblivion .kf import not supported")

        # import text keys
        self.import_text_keys(kf_root)

        # go over all controlled blocks
        for controlledblock in kf_root.controlled_blocks:
            # get the name
            nodename = controlledblock.get_node_name()
            # match from nif tree?
            node = root.find(block_name=nodename)
            if not node:
                NifLog.info("Animation for {0} but no such node found in nif tree".format(nodename))
                continue
            # node found, now find the controller
            controller_type = controlledblock.get_controller_type().decode()
            if not controller_type:
                NifLog.info("Animation for {0} without controller type, so skipping".format(nodename))
                continue
            controller = nif_utils.find_controller(node, getattr(NifFormat, controller_type))
            if not controller:
                NifLog.info("No {1} Controller found in corresponding animation node {0}, creating one".format(controller_type, nodename))
                controller = getattr(NifFormat, controller_type)()

                # TODO [animation] Set all the fields of this controller
                node.add_controller(controller)
            # yes! attach interpolator
            controller.interpolator = controlledblock.interpolator
            # in case of a NiTransformInterpolator without a data block
            # we still must re-export the interpolator for Oblivion to
            # accept the file
            # so simply add dummy keyframe data for this one with just a single
            # key to flag the exporter to export the keyframe as interpolator
            # (i.e. length 1 keyframes are simply interpolators)
            if isinstance(controller.interpolator,
                          NifFormat.NiTransformInterpolator) and controller.interpolator.data is None:
                # create data block
                kfi = controller.interpolator
                kfi.data = NifFormat.NiTransformData()
                # fill with info from interpolator
                kfd = controller.interpolator.data
                # copy rotation
                kfd.num_rotation_keys = 1
                kfd.rotation_type = NifFormat.KeyType.LINEAR_KEY
                kfd.quaternion_keys.update_size()
                kfd.quaternion_keys[0].time = 0.0
                kfd.quaternion_keys[0].value.x = kfi.rotation.x
                kfd.quaternion_keys[0].value.y = kfi.rotation.y
                kfd.quaternion_keys[0].value.z = kfi.rotation.z
                kfd.quaternion_keys[0].value.w = kfi.rotation.w
                # copy translation
                if kfi.translation.x < -1000000:
                    # invalid, happens in fallout 3, e.g. h2haim.kf
                    NifLog.warn("Ignored NaN in interpolator translation")
                else:
                    kfd.translations.num_keys = 1
                    kfd.translations.keys.update_size()
                    kfd.translations.keys[0].time = 0.0
                    kfd.translations.keys[0].value.x = kfi.translation.x
                    kfd.translations.keys[0].value.y = kfi.translation.y
                    kfd.translations.keys[0].value.z = kfi.translation.z
                # ignore scale, usually contains invalid data in interpolator

            # save priority for future reference
            # (priorities will be stored into the name of a TRANSFORM constraint on
            # bones, see import_armature function)
            # This name is a bytestring, not a string
            armature.DICT_BONE_PRIORITIES[nodename] = controlledblock.priority

        # DEBUG: save the file for manual inspection
        # niffile = open("C:\\test.nif", "wb")
        # NifFormat.write(niffile, version = 0x14000005, user_version = 11, roots = [root])

    # import animation groups
    def import_text_keys(self, n_block):
        """Stores the text keys that define animation start and end in a text
        buffer, so that they can be re-exported. Since the text buffer is
        cleared on each import only the last import will be exported
        correctly."""

        if isinstance(n_block, NifFormat.NiControllerSequence):
            txk = n_block.text_keys
        else:
            txk = n_block.find(block_type=NifFormat.NiTextKeyExtraData)
        if txk:
            # get animation text buffer, and clear it if it already exists
            # TODO [animation] Get rid of try-except block here
            try:
                animtxt = bpy.data.texts["Anim"]
                animtxt.clear()
            except KeyError:
                animtxt = bpy.data.texts.new("Anim")

            frame = 1
            for key in txk.text_keys:
                newkey = str(key.value).replace('\r\n', '/').rstrip('/')
                frame = 1 + int(key.time * animation.FPS + 0.5)  # time 0.0 is frame 1
                animtxt.write('%i/%s\n' % (frame, newkey))

            # set start and end frames
            bpy.context.scene.frame_start = 1
            bpy.context.scene.frame_end = frame

    def get_frames_per_second(self, roots):
        """Scan all blocks and return a reasonable number for FPS."""
        # find all key times
        key_times = []
        for root in roots:
            for kfd in root.tree(block_type=NifFormat.NiKeyframeData):
                key_times.extend(key.time for key in kfd.translations.keys)
                key_times.extend(key.time for key in kfd.scales.keys)
                key_times.extend(key.time for key in kfd.quaternion_keys)
                key_times.extend(key.time for key in kfd.xyz_rotations[0].keys)
                key_times.extend(key.time for key in kfd.xyz_rotations[1].keys)
                key_times.extend(key.time for key in kfd.xyz_rotations[2].keys)
            for kfi in root.tree(block_type=NifFormat.NiBSplineInterpolator):
                if not kfi.basis_data:
                    # skip bsplines without basis data (eg bowidle.kf in Oblivion)
                    continue
                key_times.extend(
                    point * (kfi.stop_time - kfi.start_time) / (kfi.basis_data.num_control_points - 2) for point in
                    range(kfi.basis_data.num_control_points - 2))
            for uvdata in root.tree(block_type=NifFormat.NiUVData):
                for uvgroup in uvdata.uv_groups:
                    key_times.extend(key.time for key in uvgroup.keys)

        # not animated, return a reasonable default
        if not key_times:
            return 30

        # calculate FPS
        fps = 30
        lowest_diff = sum(abs(int(time * fps + 0.5) - (time * fps))
                          for time in key_times)
        # for test_fps in range(1,120): #disabled, used for testing
        for test_fps in [20, 25, 35]:
            diff = sum(abs(int(time * test_fps + 0.5) - (time * test_fps))
                       for time in key_times)
            if diff < lowest_diff:
                lowest_diff = diff
                fps = test_fps
        NifLog.info("Animation estimated at %i frames per second." % fps)
        return fps

    def store_animation_data(self, rootBlock):
        return
        # very slow, implement later
        """
        niBlockList = [block for block in rootBlock.tree() if isinstance(block, NifFormat.NiAVObject)]
        for niBlock in niBlockList:
            kfc = nif_utils.find_controller(niBlock, NifFormat.NiKeyframeController)
            if not kfc: continue
            kfd = kfc.data
            if not kfd: continue
            _ANIMATION_DATA.extend([{'data': key, 'block': niBlock, 'frame': None} for key in kfd.translations.keys])
            _ANIMATION_DATA.extend([{'data': key, 'block': niBlock, 'frame': None} for key in kfd.scales.keys])
            if kfd.rotation_type == 4:
                _ANIMATION_DATA.extend([{'data': key, 'block': niBlock, 'frame': None} for key in kfd.xyz_rotations.keys])
            else:
                _ANIMATION_DATA.extend([{'data': key, 'block': niBlock, 'frame': None} for key in kfd.quaternion_keys])

        # set the frames in the _ANIMATION_DATA list
        for key in _ANIMATION_DATA:
            # time 0 is frame 1
            key['frame'] = 1 + int(key['data'].time * animation.FPS + 0.5)

        # sort by frame, I need this later
        _ANIMATION_DATA.sort(lambda key1, key2: cmp(key1['frame'], key2['frame']))
        """

    def set_animation(self, n_block, b_obj):
        """Load basic animation info for this object."""
        kfc = nif_utils.find_controller(n_block, NifFormat.NiKeyframeController)
        if not kfc:
            # no animation data: do nothing
            return

        if kfc.interpolator:
            if isinstance(kfc.interpolator, NifFormat.NiBSplineInterpolator):
                kfd = None  # not supported yet so avoids fatal error - should be kfc.interpolator.spline_data when spline data is figured out.
            else:
                kfd = kfc.interpolator.data
        else:
            kfd = kfc.data

        if not kfd:
            # no animation data: do nothing
            return

        # denote progress
        NifLog.info("Animation")
        NifLog.info("Importing animation data for {0}".format(b_obj.name))
        assert (isinstance(kfd, NifFormat.NiKeyframeData))
        # get the animation keys
        translations = kfd.translations
        scales = kfd.scales
        # add the keys

        # Create curve structure
        if b_obj.animation_data is None:
            b_obj.animation_data_create()
        b_obj_action = bpy.data.actions.new(str(b_obj.name) + "-Anim")
        b_obj.animation_data.action = b_obj_action

        NifLog.debug('Scale keys...')
        for key in scales.keys:
            frame = 1 + int(key.time * animation.FPS + 0.5)  # time 0.0 is frame 1
            bpy.context.scene.frame_set(frame)
            b_obj.scale = (key.value, key.value, key.value)
            b_obj.keyframe_insert('scale')

        # detect the type of rotation keys
        rotation_type = kfd.rotation_type
        if rotation_type == 4:
            # uses xyz rotation
            xkeys = kfd.xyz_rotations[0].keys
            ykeys = kfd.xyz_rotations[1].keys
            zkeys = kfd.xyz_rotations[2].keys
            NifLog.debug('Rotation keys...(euler)')
            for (xkey, ykey, zkey) in zip(xkeys, ykeys, zkeys):
                frame = 1 + int(xkey.time * animation.FPS + 0.5)  # time 0.0 is frame 1
                # XXX we assume xkey.time == ykey.time == zkey.time
                bpy.context.scene.frame_set(frame)
                # both in radians, no conversion needed
                b_obj.rotation_euler = (xkey.value, ykey.value, zkey.value)
                b_obj.keyframe_insert('rotation_euler')
        else:
            # uses quaternions
            if kfd.quaternion_keys:
                NifLog.debug('Rotation keys...(quaternions)')
            for key in kfd.quaternion_keys:
                frame = 1 + int(key.time * animation.FPS + 0.5)  # time 0.0 is frame 1
                bpy.context.scene.frame_set(frame)
                # Blender euler is now in radians, not degrees
                rot = mathutils.Quaternion((key.value.w, key.value.x, key.value.y, key.value.z)).toEuler()
                b_obj.rotation_euler = (rot.x, rot.y, rot.z)
                b_obj.keyframe_insert('rotation_euler')

        if translations.keys:
            NifLog.debug('Translation keys...')
        for key in translations.keys:
            frame = 1 + int(key.time * animation.FPS + 0.5)  # time 0.0 is frame 1
            bpy.context.scene.frame_set(frame)
            b_obj.location = (key.value.x, key.value.y, key.value.z)
            b_obj.keyframe_insert('location')

        bpy.context.scene.frame_set(1)


# TODO: Is there a better way to this than return a string,
#       since handling requires different code per type?
def get_extend_from_flags(flags):
    if flags & 6 == 4:  # 0b100
        return "CONST"
    elif flags & 6 == 0:  # 0b000
        return "CYCLIC"

    NifLog.warn("Unsupported cycle mode in nif, using clamped.")
    return "CONST"


def get_b_curve_from_n_curve(n_ipo_type):
    if n_ipo_type == NifFormat.KeyType.LINEAR_KEY:
        return bpy.types.Keyframe.interpolation.LINEAR
    elif n_ipo_type == NifFormat.KeyType.QUADRATIC_KEY:
        return bpy.types.Keyframe.interpolation.BEZIER
    elif n_ipo_type == 0:
        # guessing, not documented in nif.xml
        return bpy.types.Keyframe.interpolation.CONST

    NifLog.warn("Unsupported interpolation mode ({0}) in nif, using quadratic/bezier.".format(n_ipo_type))
    return bpy.types.Keyframe.interpolation.BEZIER


class ObjectAnimation:

    def get_object_ipo(self, b_object):
        """Return existing object ipo data, or if none exists, create one
        and return that.
        """
        if not b_object.ipo:
            b_object.ipo = Blender.Ipo.New("Object", "Ipo")
        return b_object.ipo

    def import_object_vis_controller(self, b_object, n_node):
        """Import vis controller for blender object."""
        n_vis_ctrl = nif_utils.find_controller(n_node, NifFormat.NiVisController)
        if not (n_vis_ctrl and n_vis_ctrl.data):
            return
        NifLog.info("Importing vis controller")
        b_channel = "Layer"
        b_ipo = self.get_object_ipo(b_object)
        b_curve = b_ipo.addCurve(b_channel)
        b_curve.interpolation = Blender.IpoCurve.InterpTypes.CONST
        b_curve.extend = get_extend_from_flags(n_vis_ctrl.flags)
        for n_key in n_vis_ctrl.data.keys:
            b_curve[1 + n_key.time * animation.FPS] = (
                    2 ** (n_key.value + max([1] + bpy.context.scene.getLayers()) - 1))


class MaterialAnimation:

    # TODO [animation] figure out where this is intended to be used
    def import_material_controllers(self, b_material, n_geom):
        """Import material animation data for given geometry."""
        if not NifOp.props.animation:
            return

        self.import_material_alpha_controller(b_material, n_geom)
        self.import_material_color_controller(
            b_material=b_material,
            b_channels=("MirR", "MirG", "MirB"),
            n_geom=n_geom,
            n_target_color=NifFormat.TargetColor.TC_AMBIENT)
        self.import_material_color_controller(
            b_material=b_material,
            b_channels=("R", "G", "B"),
            n_geom=n_geom,
            n_target_color=NifFormat.TargetColor.TC_DIFFUSE)
        self.import_material_color_controller(
            b_material=b_material,
            b_channels=("SpecR", "SpecG", "SpecB"),
            n_geom=n_geom,
            n_target_color=NifFormat.TargetColor.TC_SPECULAR)
        self.import_material_uv_controller(b_material, n_geom)

    def import_material_alpha_controller(self, b_material, n_geom):
        # find alpha controller
        n_matprop = nif_utils.find_property(n_geom, NifFormat.NiMaterialProperty)
        if not n_matprop:
            return
        n_alphactrl = nif_utils.find_controller(n_matprop, NifFormat.NiAlphaController)
        if not (n_alphactrl and n_alphactrl.data):
            return
        NifLog.info("Importing alpha controller")
        b_channel = "Alpha"
        b_ipo = self.get_material_ipo(b_material)
        b_curve = b_ipo.addCurve(b_channel)
        b_curve.interpolation = get_b_curve_from_n_curve(
            n_alphactrl.data.data.interpolation)
        b_curve.extend = get_extend_from_flags(n_alphactrl.flags)
        for n_key in n_alphactrl.data.data.keys:
            b_curve[1 + n_key.time * animation.FPS] = n_key.value

    def import_material_color_controller(self, b_material, b_channels, n_geom, n_target_color):
        # find material color controller with matching target color
        n_matprop = nif_utils.find_property(n_geom, NifFormat.NiMaterialProperty)
        if not n_matprop:
            return
        for ctrl in n_matprop.get_controllers():
            if isinstance(ctrl, NifFormat.NiMaterialColorController):
                if ctrl.get_target_color() == n_target_color:
                    n_matcolor_ctrl = ctrl
                    break
        else:
            return
        NifLog.info(
            "Importing material color controller for target color {0} into blender channels {0}".format(n_target_color,
                                                                                                        b_channels))
        # import data as curves
        b_ipo = self.get_material_ipo(b_material)
        for i, b_channel in enumerate(b_channels):
            b_curve = b_ipo.addCurve(b_channel)
            b_curve.interpolation = get_b_curve_from_n_curve(
                n_matcolor_ctrl.data.data.interpolation)
            b_curve.extend = get_extend_from_flags(n_matcolor_ctrl.flags)
            for n_key in n_matcolor_ctrl.data.data.keys:
                b_curve[1 + n_key.time * animation.FPS] = n_key.value.as_list()[i]

    def import_material_uv_controller(self, b_material, n_geom):
        """Import UV controller data."""
        # search for the block
        n_ctrl = nif_utils.find_controller(n_geom, NifFormat.NiUVController)
        if not (n_ctrl and n_ctrl.data):
            return
        NifLog.info("Importing UV controller")
        b_channels = ("OfsX", "OfsY", "SizeX", "SizeY")
        for b_channel, n_uvgroup in zip(b_channels, n_ctrl.data.uv_groups):
            if n_uvgroup.keys:
                # create curve in material ipo
                b_ipo = self.get_material_ipo(b_material)
                b_curve = b_ipo.addCurve(b_channel)
                b_curve.interpolation = get_b_curve_from_n_curve(
                    n_uvgroup.interpolation)
                b_curve.extend = get_extend_from_flags(n_ctrl.flags)
                for n_key in n_uvgroup.keys:
                    if b_channel.startswith("Ofs"):
                        # offsets are negated
                        b_curve[1 + n_key.time * animation.FPS] = -n_key.value
                    else:
                        b_curve[1 + n_key.time * animation.FPS] = n_key.value

    def get_material_ipo(self, b_material):
        """Return existing material ipo data, or if none exists, create one
        and return that.
        """
        if not b_material.ipo:
            b_material.ipo = Blender.Ipo.New("Material", "MatIpo")
        return b_material.ipo


class ArmatureAnimation:

    def import_armature_animation(self, b_armature):
        # current blender adds pose_bone keyframes to an fcurve in the armature's OBJECT
        # data block, not the ARMATURE's data block. So, rna path (data_path) for fcurves
        # will be  "pose.bones["bone name"].fcurvetype" with implicit "object." at front.
        # Get object with bpy.data.objects[b_armature.name]
        # create an action
        b_armature_object = bpy.data.objects[b_armature.name]
        b_armature_object.animation_data_create()
        b_armature_action = bpy.data.actions.new(str(b_armature.name) + "-kfAnim")
        b_armature_object.animation_data.action = b_armature_action
        # go through all armature pose bones
        NifLog.info('Importing Animations')
        for bone_name, b_posebone in b_armature.pose.bones.items():
            # denote progress
            NifLog.debug('Importing animation for bone %s'.format(bone_name))
            niBone = blocks.DICT_BLOCKS[bone_name]

            # get bind matrix (NIF format stores full transformations in keyframes,
            # but Blender wants relative transformations, hence we need to know
            # the bind position for conversion). Since
            # [ SRchannel 0 ]    [ SRbind 0 ]   [ SRchannel * SRbind         0 ]   [ SRtotal 0 ]
            # [ Tchannel  1 ] *  [ Tbind  1 ] = [ Tchannel  * SRbind + Tbind 1 ] = [ Ttotal  1 ]
            # with
            # 'total' the transformations as stored in the NIF keyframes,
            # 'bind' the Blender bind pose, and
            # 'channel' the Blender IPO channel,
            # it follows that
            # Schannel = Stotal / Sbind
            # Rchannel = Rtotal * inverse(Rbind)
            # Tchannel = (Ttotal - Tbind) * inverse(Rbind) / Sbind
            bone_bm = nif_utils.import_matrix(niBone)  # base pose
            niBone_bind_scale, niBone_bind_rot, niBone_bind_trans = nif_utils.decompose_srt(bone_bm)
            niBone_bind_rot_inv = mathutils.Matrix(niBone_bind_rot)
            niBone_bind_rot_inv.invert()
            niBone_bind_quat_inv = niBone_bind_rot_inv.to_quaternion()
            # we also need the conversion of the original matrix to the
            # new bone matrix, say X,
            # B' = X * B
            # (with B' the Blender matrix and B the NIF matrix) because we
            # need that
            # C' * B' = X * C * B
            # and therefore
            # C' = X * C * B * inverse(B') = X * C * inverse(X),
            # where X = B' * inverse(B)
            #
            # In detail:
            # [ SRX 0 ]   [ SRC 0 ]            [ SRX 0 ]
            # [ TX  1 ] * [ TC  1 ] * inverse( [ TX  1 ] ) =
            # [ SRX * SRC       0 ]   [ inverse(SRX)         0 ]
            # [ TX * SRC + TC   1 ] * [ -TX * inverse(SRX)   1 ] =
            # [ SRX * SRC * inverse(SRX)              0 ]
            # [ (TX * SRC + TC - TX) * inverse(SRX)   1 ]
            # Hence
            # SC' = SX * SC / SX = SC
            # RC' = RX * RC * inverse(RX)
            # TC' = (TX * SC * RC + TC - TX) * inverse(RX) / SX
            extra_matrix_scale, extra_matrix_rot, extra_matrix_trans = nif_utils.decompose_srt(armature.dict_bones_extra_matrix[niBone])
            extra_matrix_quat = extra_matrix_rot.to_quaternion()
            extra_matrix_rot_inv = mathutils.Matrix(extra_matrix_rot)
            extra_matrix_rot_inv.invert()
            extra_matrix_quat_inv = extra_matrix_rot_inv.to_quaternion()
            # now import everything
            # ##############################

            # get controller, interpolator, and data
            # note: the NiKeyframeController check also includes
            #       NiTransformController (see hierarchy!)
            kfc = nif_utils.find_controller(niBone, NifFormat.NiKeyframeController)
            # old style: data directly on controller
            kfd = kfc.data if kfc else None
            # new style: data via interpolator
            kfi = kfc.interpolator if kfc else None
            # next is a quick hack to make the new transform
            # interpolator work as if it is an old style keyframe data
            # block parented directly on the controller
            if isinstance(kfi, NifFormat.NiTransformInterpolator):
                kfd = kfi.data
                # for now, in this case, ignore interpolator
                kfi = None

            # B-spline curve import
            if isinstance(kfi, NifFormat.NiBSplineInterpolator):
                times = list(kfi.get_times())
                translations = list(kfi.get_translations())
                scales = list(kfi.get_scales())
                rotations = list(kfi.get_rotations())

                # if we have translation keys, we make a dictionary of
                # rot_keys and scale_keys, this makes the script work MUCH
                # faster in most cases
                if translations:
                    scale_keys_dict = {}
                    rot_keys_dict = {}

                # scales: ignore for now, implement later
                #         should come here
                # TODO: Was this skipped for a reason? Just copy from keyframe type below?
                scales = None

                # rotations
                if rotations:
                    NifLog.debug('Rotation keys...(bspline quaternions)')
                    for time, quat in zip(times, rotations):
                        frame = 1 + int(time * animation.fps + 0.5)
                        quat = mathutils.Quaternion(
                            [quat[0], quat[1], quat[2], quat[3]])

                        quatVal = niBone_bind_quat_inv.cross(quat)
                        rot = extra_matrix_quat_inv.cross(quatVal)
                        rot = rot.cross(extra_matrix_quat)

                        b_posebone.rotation_quaternion = rot
                        b_posebone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=bone_name)
                        # fill optimizer dictionary
                        if translations:
                            rot_keys_dict[frame] = mathutils.Quaternion(rot)

                # translations
                if translations:
                    NifLog.debug('Translation keys...(bspline)')
                    for time, translation in zip(times, translations):
                        # time 0.0 is frame 1
                        frame = 1 + int(time * animation.FPS + 0.5)
                        trans = mathutils.Vector(*translation)
                        locVal = (1.0 / niBone_bind_scale) * niBone_bind_rot_inv * (trans - niBone_bind_trans)  # Tchannel = (Ttotal - Tbind) * inverse(Rbind) / Sbind
                        # the rotation matrix is needed at this frame (that's
                        # why the other keys are inserted first)
                        if rot_keys_dict:
                            try:
                                rot = rot_keys_dict[frame].to_matrix()
                            except KeyError:
                                # fall back on slow method
                                # apparently, spline interpolators only have quaternion (?)
                                fcurves = b_armature_action.groups[bone_name].channels
                                quat = mathutils.Quaternion()
                                # If there are no rotation keys, the quaternion will just be 1,0,0,0  so fine anyway
                                for fc in fcurves:
                                    if "rotation_quaternion" in fc.data_path:
                                        if fc.array_index == 0: quat.w = fc.evaluate(frame)
                                        if fc.array_index == 1: quat.x = fc.evaluate(frame)
                                        if fc.array_index == 2: quat.y = fc.evaluate(frame)
                                        if fc.array_index == 3: quat.z = fc.evaluate(frame)
                                rot = quat.to_matrix()
                        else:
                            rot = mathutils.Matrix([[1.0, 0.0, 0.0],
                                                    [0.0, 1.0, 0.0],
                                                    [0.0, 0.0, 1.0]])
                        # we also need the scale at this frame
                        if scale_keys_dict:
                            try:
                                size_val = scale_keys_dict[frame]
                            except KeyError:
                                fcurves = bpy.data.actions[str(b_armature.name) + "Action"].groups[bone_name].channels
                                for fc in fcurves:
                                    if fc.data_path == "scale":
                                        sizeVal = fc.evaluate(frame)
                                else:
                                    size_val = 1.0
                        else:
                            sizeVal = 1.0
                        size = mathutils.Matrix([[sizeVal, 0.0, 0.0],
                                                 [0.0, sizeVal, 0.0],
                                                 [0.0, 0.0, sizeVal]])

                        # now we can do the final calculation
                        loc = (extra_matrix_rot_inv * (1.0 / extra_matrix_scale)) * (
                                rot * size * extra_matrix_trans + locVal - extra_matrix_trans)  # C' = X * C * inverse(X)
                        b_posebone.location = loc
                        b_posebone.keyframe_insert(data_path="location", frame=frame, group=bone_name)

                # delete temporary dictionaries
                if translations:
                    del scale_keys_dict
                    del rot_keys_dict

            # NiKeyframeData and NiTransformData import
            elif isinstance(kfd, NifFormat.NiKeyframeData):

                translations = kfd.translations
                scales = kfd.scales
                # if we have translation keys, we make a dictionary of
                # rot_keys and scale_keys, this makes the script work MUCH
                # faster in most cases
                if translations:
                    scale_keys_dict = {}
                    rot_keys_dict = {}
                # add the keys

                # Scaling
                if scales.keys:
                    NifLog.debug('Scale keys...')
                    for scaleKey in scales.keys:
                        # time 0.0 is frame 1
                        frame = 1 + int(scaleKey.time * animation.fps + 0.5)
                        sizeVal = scaleKey.value
                        size = sizeVal / niBone_bind_scale  # Schannel = Stotal / Sbind
                        b_posebone.scale = mathutils.Vector(size, size, size)
                        b_posebone.keyframe_insert(data_path="scale", frame=frame, group=bone_name)
                        # fill optimizer dictionary
                        if translations:
                            scale_keys_dict[frame] = size

                # detect the type of rotation keys
                rotation_type = kfd.rotation_type

                # Euler Rotations
                if rotation_type == 4:
                    # uses xyz rotation
                    if kfd.xyz_rotations[0].keys:
                        NifLog.debug('Rotation keys...(euler)')
                        for xkey, ykey, zkey in zip(kfd.xyz_rotations[0].keys,
                                                    kfd.xyz_rotations[1].keys,
                                                    kfd.xyz_rotations[2].keys):
                            # time 0.0 is frame 1
                            # XXX it is assumed that all the keys have the
                            # XXX same times!!!
                            if abs(xkey.time - ykey.time) > self.properties.epsilon or abs(
                                    xkey.time - zkey.time) > self.properties.epsilon:
                                NifLog.warn("XYZ key times do not correspond, animation may not be correctly imported")
                            frame = 1 + int(xkey.time * animation.fps + 0.5)
                            # blender now uses radians for euler
                            euler = mathutils.Euler(xkey.value, ykey.value, zkey.value)
                            quat = euler.to_quaternion()

                            quatVal = quat.cross(niBone_bind_quat_inv)
                            rot = extra_matrix_quat_inv.cross(quatVal)
                            rot = rot.cross(extra_matrix_quat)

                            b_posebone.rotation_quaternion = rot
                            b_posebone.keyframe_insert(data_path="rotation_euler", frame=frame, group=bone_name)
                            # fill optimizer dictionary
                            if translations:
                                rot_keys_dict[frame] = mathutils.Quaternion(rot)

                                # Quaternion Rotations
                else:
                    # TODO [animation] Take rotation type into account for interpolation
                    if kfd.quaternion_keys:
                        NifLog.debug('Rotation keys...(quaternions)')
                        quaternion_keys = kfd.quaternion_keys
                        for key in quaternion_keys:
                            frame = 1 + int(key.time * armature.fps + 0.5)
                            keyVal = key.value
                            quat = mathutils.Quaternion([keyVal.w, keyVal.x, keyVal.y, keyVal.z])

                            quatVal = niBone_bind_quat_inv.cross(quat)
                            rot = extra_matrix_quat_inv.cross(quatVal)
                            rot = rot.cross(extra_matrix_quat)

                            b_posebone.rotation_quaternion = rot
                            b_posebone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=bone_name)
                            # fill optimizer dictionary
                            if translations:
                                rot_keys_dict[frame] = mathutils.Quaternion(rot)
                        # else:
                        #    print("Rotation keys...(unknown)" +
                        #          "WARNING: rotation animation data of type" +
                        #          " %i found, but this type is not yet supported; data has been skipped""" % rotation_type)

                # Translations
                if translations.keys:
                    NifLog.debug('Translation keys...')
                    for key in translations.keys:
                        # time 0.0 is frame 1
                        frame = 1 + int(key.time * armature.fps + 0.5)
                        keyVal = key.value
                        trans = mathutils.Vector((keyVal.x, keyVal.y, keyVal.z))
                        locVal = (niBone_bind_rot_inv * (1.0 / niBone_bind_scale)) * (trans - niBone_bind_trans)
                        # the rotation matrix is needed at this frame (that's
                        # why the other keys are inserted first)
                        if rot_keys_dict:
                            try:
                                rot = rot_keys_dict[frame].to_matrix()
                            except KeyError:
                                # fall back on slow method
                                fcurves = b_armature_action.groups[bone_name].channels
                                quat = mathutils.Quaternion()
                                euler = None
                                # If there are no rotation keys, the quaternion will just be 1,0,0,0  so fine anyway
                                for fc in fcurves:
                                    if "rotation_quaternion" in fc.data_path:
                                        if fc.array_index == 0: quat.w = fc.evaluate(frame)
                                        if fc.array_index == 1: quat.x = fc.evaluate(frame)
                                        if fc.array_index == 2: quat.y = fc.evaluate(frame)
                                        if fc.array_index == 3: quat.z = fc.evaluate(frame)
                                    elif "rotation_euler" in fc.data_path:
                                        euler = mathutils.Euler()
                                        if fc.array_index == 0: euler.x = fc.evaluate(frame)
                                        if fc.array_index == 1: euler.y = fc.evaluate(frame)
                                        if fc.array_index == 2: euler.z = fc.evaluate(frame)
                                if euler is not None:
                                    quat = euler.to_quaternion()
                                rot = quat.to_matrix()
                        else:
                            rot = mathutils.Matrix([[1.0, 0.0, 0.0],
                                                    [0.0, 1.0, 0.0],
                                                    [0.0, 0.0, 1.0]])
                        # we also need the scale at this frame
                        if scale_keys_dict:
                            try:
                                sizeVal = scale_keys_dict[frame]
                            except KeyError:
                                fcurves = bpy.data.actions[str(b_armature.name) + "-kfAnim"].groups[bone_name].channels
                                # If there is no fcurve, size will just be 1.0
                                sizeVal = 1.0
                                for fc in fcurves:
                                    if fc.data_path == "scale":
                                        sizeVal = fc.evaluate(frame)
                        else:
                            sizeVal = 1.0
                        size = mathutils.Matrix([[sizeVal, 0.0, 0.0],
                                                 [0.0, sizeVal, 0.0],
                                                 [0.0, 0.0, sizeVal]])
                        # now we can do the final calculation
                        loc = (extra_matrix_rot_inv * (1.0 / extra_matrix_scale)) * (
                                rot * size * extra_matrix_trans + locVal - extra_matrix_trans)  # C' = X * C * inverse(X)
                        b_posebone.location = loc
                        b_posebone.keyframe_insert(data_path="location", frame=frame, group=bone_name)

                if translations:
                    del scale_keys_dict
                    del rot_keys_dict

            # set extend mode for all fcurves
            if kfc:
                if bone_name in b_armature_action.groups:
                    bone_fcurves = b_armature_action.groups[bone_name].channels
                    f_curve_extend_type = get_extend_from_flags(kfc.flags)
                    if f_curve_extend_type == "CONST":
                        for fcurve in bone_fcurves:
                            fcurve.extrapolation = 'CONSTANT'
                    elif f_curve_extend_type == "CYCLIC":
                        for fcurve in bone_fcurves:
                            fcurve.modifiers.new('CYCLES')
                    else:
                        for fcurve in bone_fcurves:
                            fcurve.extrapolation = 'CONSTANT'


class GeometryAnimation:

    @staticmethod
    def process_geometry_animation(applytransform, b_mesh, n_block, transform, v_map):
        morph_ctrl = nif_utils.find_controller(n_block, NifFormat.NiGeomMorpherController)
        if morph_ctrl:
            morph_data = morph_ctrl.data
            if morph_data.num_morphs:
                # insert base key at frame 1, using relative keys
                b_mesh.insertKey(1, 'relative')
                # get name for base key
                keyname = morph_data.morphs[0].frame_name
                if not keyname:
                    keyname = 'Base'
                # set name for base key
                b_mesh.key.blocks[0].name = keyname
                # get base vectors and import all morphs
                baseverts = morph_data.morphs[0].vectors
                b_ipo = Blender.Ipo.New('Key', 'KeyIpo')
                b_mesh.key.ipo = b_ipo
                for idxMorph in range(1, morph_data.num_morphs):
                    # get name for key
                    keyname = morph_data.morphs[idxMorph].frame_name
                    if not keyname:
                        keyname = 'Key %i' % idxMorph
                    NifLog.info("Inserting key '{0}'".format(keyname))
                    # get vectors
                    morphverts = morph_data.morphs[idxMorph].vectors
                    # for each vertex calculate the key position from base
                    # pos + delta offset
                    assert (len(baseverts) == len(morphverts) == len(v_map))
                    for bv, mv, b_v_index in zip(baseverts, morphverts, v_map):
                        base = mathutils.Vector(bv.x, bv.y, bv.z)
                        delta = mathutils.Vector(mv.x, mv.y, mv.z)
                        v = base + delta
                        if applytransform:
                            v *= transform
                        b_mesh.vertices[b_v_index].co[0] = v.x
                        b_mesh.vertices[b_v_index].co[1] = v.y
                        b_mesh.vertices[b_v_index].co[2] = v.z
                    # update the mesh and insert key
                    b_mesh.insertKey(idxMorph, 'relative')
                    # set name for key
                    b_mesh.key.blocks[idxMorph].name = keyname
                    # set up the ipo key curve
                    try:
                        b_curve = b_ipo.addCurve(keyname)
                    except ValueError:
                        # this happens when two keys have the same name
                        # an instance of this is in fallout 3
                        # meshes/characters/_male/skeleton.nif HeadAnims:0
                        NifLog.warn("Skipped duplicate of key '{0}'".format(keyname))
                    # no idea how to set up the bezier triples -> switching
                    # to linear instead
                    b_curve.interpolation = Blender.IpoCurve.InterpTypes.LINEAR
                    # select extrapolation
                    b_curve.extend = animation.get_extend_from_flags(morph_ctrl.flags)
                    # set up the curve's control points
                    # first find the keys
                    # older versions store keys in the morphData
                    morph_keys = morph_data.morphs[idxMorph].keys
                    # newer versions store keys in the controller
                    if (not morph_keys) and morph_ctrl.interpolators:
                        morph_keys = morph_ctrl.interpolators[idxMorph].data.data.keys
                    for key in morph_keys:
                        x = key.value
                        frame = 1 + int(key.time * animation.FPS + 0.5)
                        b_curve.addBezier((frame, x))
                    # finally: return to base position
                    for bv, b_v_index in zip(baseverts, v_map):
                        base = mathutils.Vector(bv.x, bv.y, bv.z)
                        if applytransform:
                            base *= transform
                        b_mesh.vertices[b_v_index].co[0] = base.x
                        b_mesh.vertices[b_v_index].co[1] = base.y
                        b_mesh.vertices[b_v_index].co[2] = base.z
        return b_ipo
