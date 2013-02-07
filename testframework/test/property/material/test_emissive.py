"""Export and import material meshes."""

import bpy
import nose.tools

from pyffi.formats.nif import NifFormat

from test import SingleNif
from test.data import gen_data
from test.geometry.trishape import gen_geometry
from test.geometry.trishape.test_geometry import TestBaseGeometry
from test.property.material import gen_material
from test.property.material.test_material import TestMaterialProperty

"""Export and import material meshes with emissive property."""
class TestEmissiveMaterial(SingleNif):
    
    n_name = "property/material/base_emissive"
    b_name = 'Cube'

    def b_create_objects(self):
        b_obj = TestBaseGeometry.b_create_base_geometry()
        b_obj = TestMaterialProperty.b_create_material_block(b_obj)
        b_obj.name = self.b_name
        
        b_mat = b_obj.data.materials[0]
        self.b_create_emmisive_property(b_mat)
    
    @classmethod
    def b_create_emmisive_property(cls, b_mat):
        b_mat.niftools.emissive_color = (0.5,0.0,0.0)
        b_mat.emit = 1.0
        return b_mat

    def b_check_data(self):
        b_obj = bpy.data.objects[self.b_name]
        TestMaterialProperty.b_check_material_block(b_obj)
        self.b_check_emissive_block(b_obj)

    @classmethod
    def b_check_emissive_block(cls, b_obj):
        b_mat = b_obj.data.materials[0]
        cls.b_check_emission_property(b_mat)

    @classmethod
    def b_check_emission_property(cls, b_mat):
        nose.tools.assert_equal(b_mat.emit, 1.0)
        nose.tools.assert_equal((b_mat.niftools.emissive_color.r,
                                 b_mat.niftools.emissive_color.g,
                                 b_mat.niftools.emissive_color.b),
                                (0.5,0.0,0.0))

    def n_create_data(self):
        self.n_data = gen_data.n_create_data(self.n_data)
        self.n_data = gen_geometry.n_create_blocks(self.n_data)
        
        n_trishape = self.n_data.roots[0].children[0]
        self.n_data.roots[0].children[0] = gen_material.n_attach_material_prop(n_trishape)
        self.n_data.roots[0].children[0].properties[0] = gen_material.n_alter_emissive(n_trishape.properties[0])
        return self.n_data


    def n_check_data(self, n_data):
        n_geom = n_data.roots[0].children[0]
        TestMaterialProperty.n_check_material_property(n_geom.properties[0])
        self.n_check_material_emissive_property(n_geom.properties[0])
        
    @classmethod
    def n_check_material_emissive_property(cls, n_mat_prop):
        # TODO - Refer to header
        nose.tools.assert_equal((n_mat_prop.emissive_color.r,
                                 n_mat_prop.emissive_color.g,
                                 n_mat_prop.emissive_color.b),
                                (0.5,0.0,0.0))
