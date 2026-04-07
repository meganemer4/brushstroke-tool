"""
Brush Stroke Effect Python Script (for Houdini & Mantra)
by Megan White

Made with Houdini 21.0 
"""

import hou
import random
from PIL import Image
import re
from PySide6 import QtWidgets, QtCore



#######################################################

class StrokeToolUI(QtWidgets.QDialog):
##### constructor for creating the UI menu #####
    def __init__(self):
        super().__init__(hou.ui.mainQtWindow())
        self.setWindowTitle("Brush Stroke Tool")
        layout = QtWidgets.QVBoxLayout()
        
        #renderer selection 
        self.renderer_combo = QtWidgets.QComboBox()
        self.renderer_combo.addItems(["Karma", "Mantra"])
        ui_add_labeled(layout, "Renderer", self.renderer_combo)
    
        #density selection
        self.density_spin = QtWidgets.QDoubleSpinBox()
        self.density_spin.setRange(0.2, 3.0)
        self.density_spin.setValue(1.0)
        ui_add_labeled(layout, "Stroke Density", self.density_spin)
        
        #scale selection        
        self.scale_spin = QtWidgets.QDoubleSpinBox()
        self.scale_spin.setRange(0.1, 3.0)
        self.scale_spin.setValue(1.2)
        ui_add_labeled(layout, "Stroke Scale", self.scale_spin)
        
        #brush 1 selection 
        self.brush1_path = QtWidgets.QLineEdit()
        btn1 = QtWidgets.QPushButton("Browse")
        btn1.clicked.connect(lambda: self.ui_pick_file(self.brush1_path))
        ui_add_labeled(layout, "Brush Texture 1:", self.brush1_path)
        layout.addWidget(btn1)   
        
        #brush 2 selection       
        self.brush2_path = QtWidgets.QLineEdit()
        btn2 = QtWidgets.QPushButton("Browse")
        btn2.clicked.connect(lambda: self.ui_pick_file(self.brush2_path))
        ui_add_labeled(layout, "Brush Texture 2:", self.brush2_path)
        layout.addWidget(btn2)
        
        #Generate button
        layout.addWidget(QtWidgets.QLabel("Generate Setup:"))
        self.build_btn = QtWidgets.QPushButton("1. Build Setup")
        layout.addWidget(self.build_btn)
        
        #load previous values
        self.ui_load_settings()
        self.setLayout(layout)
        self.build_btn.clicked.connect(self.build)


    ### UI methods
    def ui_pick_file(self, field):
        path = QtWidgets.QFileDialog.getOpenFileName(self, "Select Texture")[0]
        if path:
            field.setText(path)

    def ui_load_settings(self): #remember brush paths from previous session
        self.brush1_path.setText(getattr(hou.session, "brush1", ""))
        self.brush2_path.setText(getattr(hou.session, "brush2", ""))

    def ui_save_settings(self):
        hou.session.brush1 = self.brush1_path.text()
        hou.session.brush2 = self.brush2_path.text()

    def ui_get_values(self):
        return {
            "renderer": self.renderer_combo.currentText().lower(),
            "density": self.density_spin.value(),
            "scale": self.scale_spin.value(),
            "brush1": self.brush1_path.text(),
            "brush2": self.brush2_path.text()
        }
         
##########################################
############# Main build  ################

    def build(self):
        selected = hou.selectedNodes()
        if not selected:
            raise hou.Error("Please select a geometry node.")
    
        values = self.ui_get_values()
        
        #some checks to work with lacking brush selections
        if not values["brush1"] and not values["brush2"]:
            hou.ui.displayMessage(
                "Please select at least one brush alpha texture before building.",
                severity=hou.severityType.Warning
            )
            return
        elif not values["brush1"] and values["brush2"]:
            values["brush1"] = values["brush2"]
        elif not values["brush2"] and values["brush1"]:
            values["brush2"] = values["brush1"]
        
        subnet, geo = self.build_create_subnet(selected, values)  
    
        stroke_mat = self.build_create_material(subnet, values)
    
        obj_list, bake_paths = self.build_create_object_merges(geo, selected)  
       
        ribbon_nodes, scatter_nodes = self.build_process_objects(geo, obj_list, bake_paths)
        
        self.build_finalize_network(geo, subnet, ribbon_nodes, scatter_nodes, stroke_mat)
        print("Build complete")

        
    ### build methods  
    
    #this creates the main subnet with the density and scale parameters for the strokes  
    def build_create_subnet(self, selected, values): 
        parent = selected[0].parent()    
        subnet = parent.createNode("subnet", parent.name() + "_painted")
        subnet.moveToGoodPosition()
    
        parm_group = subnet.parmTemplateGroup()    
        parm_group.append(hou.FloatParmTemplate(  #adds adjuster for the density of the strokes
            "stroke_density", "Stroke Density", 1,
            default_value=(values["density"],), min=0.2, max=3.0
        ))
    
        parm_group.append(hou.FloatParmTemplate( #adds adjuster for the scale of the strokes
            "stroke_scale", "Stroke Scale", 1,
            default_value=(values["scale"],), min=0.1, max=3.0
        ))
    
        subnet.setParmTemplateGroup(parm_group)    
        geo = subnet.createNode("geo", "geometry")
    
        return subnet, geo        
        
    ### creates the materials for the brush strokes depending on chosen renderer    
    def build_create_material(self, subnet, values):
        if values["renderer"] == "mantra":
            return create_mantra_material(subnet, values["brush1"], values["brush2"])
        return create_karma_material(subnet, values["brush1"], values["brush2"])
        
    ### loads the models in with obj merges        
    def build_create_object_merges(self, geo, selected):
        obj_list = []
        bake_paths = {}
    
        for i, sel in enumerate(selected):
            name = re.sub(r'[^a-zA-Z0-9_]', '_', sel.name())
            bake_path = f"$HIP/bake/{name}_diffuse.png" #bake path determined for assets that are untextured and need textures baked 
    
            obj = geo.createNode("object_merge", f"obj_merge_{i}")
            obj.parm("objpath1").set(sel.path())
            obj.parm("xformtype").set(1)
    
            obj_list.append(obj)
            bake_paths[obj] = bake_path
    
        return obj_list, bake_paths   
        
    ### creates the nodes that build out the brush strokes    
    def build_process_objects(self, geo, obj_list, bake_paths):
        ribbon_nodes = []
        scatter_nodes = []
    
        for count, source_node in enumerate(obj_list):
    
            attrs = { #dict with common attributes for cleaner script 
                "geo": geo,
                "geom": source_node.geometry(),
                "source_node": source_node,
                "count": count,
                "bake_path": bake_paths[source_node],
                "uv_attrib": source_node.geometry().findVertexAttrib("uv")
            }
            
            #generate uvs for models that do not have them
            uv_node_input, uv_output = geo_add_uvs(attrs)
    
            #identifies textures for each model
            texture_path, attrib_map = tex_identify_texture(attrs, uv_output, uv_node_input)
    
            #texture is baked from base_color if asset does not have a texture. 
            if texture_path:
                print("Texture found, using existing texture")
                final_texture = texture_path
                if attrib_map:
                    attrib_map.cook(force=True)
            else:
                print("No texture found, baking texture from basecolor")
                baker = tex_bake_shader(attrs, uv_node_input, uv_output, texture_path, attrib_map) #function for baking the shaders 
                baker.parm("execute").pressButton()
                final_texture = attrs["bake_path"]
        
            #brush stroke scatter created
            scatter = geo_create_scatter_points(attrs, uv_node_input, uv_output, final_texture)
            scatter_nodes.append(scatter)
    
            #brush stroke geo functions
            ribbon = ribbon_functions(attrs, scatter)
            ribbon = ribbon_shrinkwrap(attrs, ribbon)
            ribbon = ribbon_add_normals(attrs, ribbon)    
            ribbon_nodes.append(ribbon)
    
        return ribbon_nodes, scatter_nodes        

    # final adjustments (merge nodes, set display, assign materials)        
    def build_finalize_network(self, geo, subnet, ribbon_nodes, scatter_nodes, stroke_mat):
        merge = geo.createNode("merge", "merge_ribbons")
    
        for i, node in enumerate(ribbon_nodes):
            merge.setInput(i, node)
    
        mat = geo.createNode("material", "assign_stroke_mat")
        mat.setInput(0, merge)
        mat.parm("shop_materialpath1").set(stroke_mat.path())
    
        mat.setDisplayFlag(True)
        mat.setRenderFlag(True)
    
        subnet.setUserData("scatters", " ".join([n.path() for n in scatter_nodes]))
    
        geo.layoutChildren()        
        
        
        
        
#########################################################
################### functions ###########################


##### function for creating widgets for UI #####
def ui_add_labeled(layout, label, widget):
    layout.addWidget(QtWidgets.QLabel(label))
    layout.addWidget(widget)
    

  
############# geo functions #################        
    
##### function for checking if UVs exist, and adding default UVs if they do not #####
def geo_add_uvs(attrs):
    geo = attrs["geo"]
    source_node = attrs["source_node"]
    count = attrs["count"]
    uv_attrib = attrs["uv_attrib"]
    if uv_attrib is None:
        print("No UVs found, generating UVs")   
        uv = geo.createNode("uvunwrap", f"auto_uvunwrap_{count}")
        uv.setInput(0, source_node)    
        uv.parm("spacing").set(0.02) 
        uv.moveToGoodPosition()
    
        uv_output = uv
        uv_node_input = True
    else:
        print("UVs found, using existing UVs")
        uv_output = source_node
        uv_node_input = False
    return uv_node_input, uv_output



##### Function for creating the particle system (scatter with baked color) #####   
def geo_create_scatter_points(attrs, uv_node_input, uv_output, texture_path):
    geo = attrs["geo"]
    source_node = attrs["source_node"]
    count = attrs["count"]

    python_sop = geo.createNode("python", f"scatter_points_{count}")

    #code inside the Python SOP
    python_code = f"""

import hou
import random
import colorsys
from PIL import Image

### functions for point generation ###
# some of these calculations are weird and I had to look them up so don't ask me to explain how they work #

def srgb_to_linear(c): #correct the colorspace of Cd to match texture
    c = c / 255.0
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055)/1.055) ** 2.4


def sample_color(prim, u, v): #samples the color values from the texture
    if not use_texture:
        return (1.0, 1.0, 1.0) 

    try:
        uv_attrib = input_geo.findVertexAttrib("uv")
        uvw = prim.attribValueAtInterior(uv_attrib, u, v)
        px = int(uvw[0] * (width - 1))
        py = int((1 - uvw[1]) * (height - 1))

        r, g, b = pixels[px, py]
        return (
            srgb_to_linear(r),
            srgb_to_linear(g),
            srgb_to_linear(b)
        )
    except:
        return (1.0, 1.0, 1.0)            


# calculates orientation for the strokes on the model
def compute_orient(N):
    up = hou.Vector3(0, 1, 0)
    if abs(N.dot(up)) > 0.99:
        up = hou.Vector3(1, 0, 0)

    tangent = up.cross(N).normalized()
    bitangent = N.cross(tangent).normalized()
    m = hou.Matrix3((tangent, bitangent, N))
    orient = hou.Quaternion(m)

    angle = random.uniform(-15, 15) #randomize brush stroke rotation
    axis = hou.Vector3(0, 0, 1)   
    q = hou.Quaternion(angle, axis)
    return orient * q  

def pick_prim(prims, areas, total_area):
    r = random.uniform(0, total_area)
    accum = 0
    for prim, area in zip(prims, areas):
        accum += area
        if accum >= r:
            return prim
        
    
def point_attrib(geo, name, default):
    if not geo.findPointAttrib(name):
        geo.addAttrib(hou.attribType.Point, name, default)
    
    
node = hou.pwd()
geo = node.geometry()
input_geo = node.inputs()[0].geometry()

geo.clear()

# compute surface area (area-based scattering)
prims = input_geo.prims()
areas = [prim.intrinsicValue("measuredarea") for prim in prims]
total_area = sum(areas)

density = hou.pwd().parent().parent().parm("stroke_density").eval()

base_density = 100
num_points = max(30, int(total_area * base_density * density))

# load baked texture path
raw_path = '{texture_path}'
texture_path = hou.expandString(raw_path)

try:
    img = Image.open(texture_path).convert("RGB")
    width, height = img.size
    pixels = img.load()
    use_texture = True
except:
    use_texture = False

point_attrib(geo, "Cd", (1.0, 1.0, 1.0))
point_attrib(geo, "N", (0.0, 1.0, 0.0))
point_attrib(geo, "orient", (0.0, 0.0, 0.0, 1.0))
point_attrib(geo, "bend", 0.0)
point_attrib(geo, "rand_id", 0.0)
point_attrib(geo, "pscale", 1.0)

    
for i in range(num_points):
    prim = pick_prim(prims, areas, total_area)
    u = random.random()
    v = random.random()
    pos = prim.positionAtInterior(u, v)

    # sample texture, convert to linear, and apply subtle hue shift 
    color = sample_color(prim, u, v)
    pt = geo.createPoint()
    h, s, v = colorsys.rgb_to_hsv(color[0], color[1], color[2])    
    hue_shift = random.uniform(-0.015, 0.015)  #adds subtle hue variation
    h = (h + hue_shift) % 1.0    
    new_color = colorsys.hsv_to_rgb(h, s, v)    
    pt.setAttribValue("Cd", new_color)
    
    #calculate normals 
    try:
        verts = prim.vertices()
        p0 = verts[0].point().position()
        p1 = verts[1].point().position()
        p2 = verts[2].point().position()
        N = (p1 - p0).cross(p2 - p0).normalized()
    except:
        N = hou.Vector3(0,1,0)
    
    pt.setPosition(pos)
    pt.setAttribValue("N", N)
    pt.setAttribValue("orient", compute_orient(N))
    
    bend = random.uniform(-5, 0.25)
    pt.setAttribValue("bend", bend)
    pt.setAttribValue("rand_id", random.random())

    pt.setAttribValue("pscale", random.uniform(0.5, 1.5))
    
"""
    python_sop.parm("python").set(python_code)

    # wire input
    if uv_node_input:
        python_sop.setInput(0, uv_output)
    else:
        python_sop.setInput(0, source_node)

    return python_sop

    
 
############ texture functions ################    

##### Function that bakes out a texture if using untextured model #####
def tex_bake_shader(attrs, uv_node_input, uv_output, texture_path, attrib_map):
    geo = attrs["geo"]
    source_node = attrs["source_node"]
    count = attrs["count"]
    bake_path = attrs["bake_path"]
                
    
    try:
        baker = geo.createNode("labs::maps_baker::5.0", f"maps_baker_{count}")
    except hou.OperationFailed:
        hou.ui.displayMessage(
            "Labs Maps Baker node does not exist in your version.\n\n"
            "Please install SideFX Labs in the launcher or use a Houdini version that includes it. (or assign a texture instead)"
        )
        return None
    baker.moveToGoodPosition()
    
    # wire it into existing nodes
    if texture_path:
        baker.setInput(0, attrib_map)    
    elif uv_node_input:
        baker.setInput(0, uv_output) 
    else:
        baker.setInput(0, source_node)
    
    # baking settings 
    baker.parm("i2Resolution1").set(1024)
    baker.parm("i2Resolution2").set(1024)
  

    # baking output path
    baker.parm("sOutputFile").set(bake_path)    
    baker.parm("bManualMode").set(0)
        
    # enable maps
    if not texture_path:
        baker.parm("bDiffuse").set(1)
        baker.parm("bVertexCd").set(0)
        baker.parm("bAO").set(0)
    else:
        baker.parm("bVertexCd").set(1)    
        baker.parm("bDiffuse").set(0)
        baker.parm("bAO").set(0)
        
    return baker



##### Function that converts textures into Cd attribute #####
def tex_apply_texture_to_cd(attrs, uv_output, texture_path, uv_node_input):

    geo = attrs["geo"]
    source_node = attrs["source_node"]
    count = attrs["count"]
    attrib_map = geo.createNode("attribfrommap", f"attrib_from_map_{count}")
    
    if uv_node_input:
        attrib_map.setInput(0, uv_output)    
    else:
        attrib_map.setInput(0, source_node)

    attrib_map.parm("filename").set(texture_path)
    attrib_map.parm("export_attribute").set("Cd")
    attrib_map.moveToGoodPosition()

    return attrib_map



##### Function that detects if a texture is assigned to a model #####
def tex_identify_texture(attrs, uv_output, uv_node_input):
    geom = attrs["geom"]
    source_node = attrs["source_node"]
    
    texture_node_types = { ### this is a list of texture node names in houdini where you may have your basecolor tex loaded in
        "texture",
        "texture::2.0",
        "uvtexture",
        "osl_texture",
        "uvtexture::2.0",
        "mtlximage",
        "mtlximage::2.0",
    }
    mat = None
    texture_path = None
    
    shop_attrib = geom.findPrimAttrib("shop_materialpath")

    if shop_attrib:
        prims = geom.prims()
        if prims:
            mat_path = prims[0].attribValue("shop_materialpath")
            mat = hou.node(mat_path)

    attrib_map = None
    if mat:
        for conn in mat.inputConnections():
            node = conn.inputNode()
            
            if node.type().name() in texture_node_types: ### first checks for textures that are directly input into shader
                for parm_name in ["map", "filename", "file"]:
                    parm = node.parm(parm_name)
                    if parm:
                        val = parm.eval()
                        if val:
                            texture_path = val
                            break

            if not texture_path: ### As fallback, checks for any textures that are not directly input into the shader 
                parent = mat.parent()          
                for node in parent.children():
                    if node.type().name() in texture_node_types:
                        for parm_name in ["map", "filename", "file"]:
                            parm = node.parm(parm_name)
                            if parm:
                                val = parm.eval()
                                if val:
                                    texture_path = val
                                    attrib_map = tex_apply_texture_to_cd(attrs, uv_output, texture_path, uv_node_input)
                                    

            if texture_path:
                attrib_map = tex_apply_texture_to_cd(attrs, uv_output, texture_path, uv_node_input)
                
    return texture_path, attrib_map


   
######### ribbon functions (stroke geo) ############# 

##### function to build ribbon geo and call ribbon functions #####     
def ribbon_functions(attrs, scatter_sop):
    count = attrs["count"]
    geo = attrs["geo"]
    
    ribbon = ribbon_create(attrs)
    ribbon = ribbon_bend(attrs, ribbon)
    ribbon = ribbon_scale(attrs, ribbon)
    ribbon = ribbon_uv(attrs, ribbon)
        
    copy_ribbons = geo.createNode("copytopoints", f"copy_ribbons_{count}")
    copy_ribbons.setInput(0, ribbon)
    copy_ribbons.setInput(1, scatter_sop)
    copy_ribbons.parm("targetattribs").set(1)
    copy_ribbons.parm("applyattribs1").set("*")
    return copy_ribbons    
        
    
    
##### function for creating brush stroke (ribbon) geo #####
def ribbon_create(attrs):
    geo = attrs["geo"]
    count = attrs["count"]
    ribbon_template = geo.createNode("grid", f"ribbon_grid_{count}")
    ribbon_template.parm("sizex").set(0.4)
    ribbon_template.parm("sizey").set(0.4)
    ribbon_template.parm("rows").set(4)
    ribbon_template.parm("cols").set(8)
    ribbon_template.parmTuple("r").set((-90, 0, 0)) 
    ribbon_template.setDisplayFlag(False)
    ribbon_template.setRenderFlag(False)
    return ribbon_template

    
##### function to UV unwrap ribbons #####    
def ribbon_uv(attrs, input_node):
    geo = attrs["geo"]
    count = attrs["count"]
    uv = geo.createNode("uvunwrap", f"uv_ribbon_{count}")
    uv.setInput(0, input_node)
    uv.parm("rz").set(90)
    uv.moveToGoodPosition()
    return uv    
    
    
    
##### function to add slight bend to ribbon geo #####    
def ribbon_bend(attrs, ribbon_template):    
    geo = attrs["geo"]
    count = attrs["count"]
    bend = geo.createNode("bend", f"bend_{count}")
    bend.setInput(0, ribbon_template)    
    bend.parm("length").set(1)
    bend.parm("dirx").set(1) 
    bend.parm("diry").set(0)
    bend.parm("dirz").set(0)
    bend.parm("bendmode").set(1) #direction mode 
    bend.parm("upangle").set(200)
    bend.parm("length").set(0.9)    
    bend.moveToGoodPosition() 
    return bend
 

    
##### function to add adjustable scale to ribbon geo #####     
def ribbon_scale(attrs, bend):
    geo = attrs["geo"]
    count = attrs["count"]
    xform = geo.createNode("xform", f"scale_ribbon_{count}")
    xform.setInput(0, bend)

    # scale driven by subnet parm
    xform.parm("scale").setExpression('ch("../../stroke_scale")')

    xform.moveToGoodPosition()
    return xform
    
    
    
##### function to add shrinkwrap effect to ribbons to match geo shape #####     
def ribbon_shrinkwrap(attrs, copy_ribbons):
    geo = attrs["geo"]
    source_node = attrs["source_node"]
    count = attrs["count"]
    
    ray = geo.createNode("ray", f"ray_{count}")
    ray.setInput(0, copy_ribbons)
    ray.setInput(1, source_node)  # project onto original geo    
    ray.parm("method").set(0)  
    ray.parm("scale").set(0.5)
    ray.parm("putnml").set(1)
    return ray
 

##### function for adding normals #####    
def ribbon_add_normals(attrs, input_node):
    geo = attrs["geo"]
    count = attrs["count"]
    normal = geo.createNode("normal", f"normal_{count}")
    normal.setInput(0, input_node)

    normal.parm("type").set(0)  

    normal.moveToGoodPosition()
    return normal    
    
   
    
############ material functions ###############    

##### function to build mantra shaders for the brush strokes #####
def create_mantra_material(subnet, brush1_path, brush2_path):
    matnet = subnet.createNode("matnet", "mantra_matnet")
    subnet.layoutChildren()

    shader = matnet.createNode("principledshader::2.0", "stroke_material")

    shader.parm("rough").set(0.4)
    shader.parm("reflect").set(.8)

    shader.parm("basecolor_usePointColor").set(0)

    bind_cd = matnet.createNode("bind", "bind_Cd")
    bind_cd.parm("parmname").set("Cd")
    bind_cd.parm("parmtype").set(6)  

    shader.setNamedInput("basecolor", bind_cd, 0)

    # alphas are randomized depending on rand_id attribute created on strokes 
    tex1 = matnet.createNode("texture", "brush_tex1")
    tex1.parm("map").set(brush1_path)
    tex2 = matnet.createNode("texture", "brush_tex2")
    tex2.parm("map").set(brush2_path)
    
    bind_rand = matnet.createNode("bind", "bind_rand")
    bind_rand.parm("parmname").set("rand_id")
    bind_rand.parm("parmtype").set(0)

    mult = matnet.createNode("mulconst", "mul_by_2")
    mult.parm("mulconst").set(2)
    mult.setInput(0, bind_rand)

    floor = matnet.createNode("floor", "floor_bias")
    floor.setInput(0, mult)

    mix = matnet.createNode("mix", "mix_textures")
    mix.setInput(0, tex1)
    mix.setInput(1, tex2)
    mix.setInput(2, floor)

    luminance = matnet.createNode("luminance", "opacity_luma") 
    luminance.setInput(0, mix)

    fit = matnet.createNode("fit", "fit_opacity") #looks better when more transparent
    fit.parm("destmax").set(0.6)
    
    fit.setInput(0, luminance)
    
    shader.setNamedInput("opaccolor", fit, 0)

    matnet.layoutChildren()

    return shader
    

##### function to build karma shaders for the brush strokes #####    
def create_karma_material(subnet, brush1_path, brush2_path):
    matnet = subnet.createNode("matnet", "karma_matnet")
    subnet.layoutChildren()
    stroke_mat = matnet.createNode("mtlxstandard_surface", "karma_paint_shader")

    geomprop = matnet.createNode("mtlxgeompropvalue", "displayColor_reader")
    geomprop.parm("geomprop").set("displayColor")
    geomprop.parm("signature").set("color3")

    stroke_mat.setNamedInput("base_color", geomprop, 0)
    stroke_mat.parm("specular").set(0.8)
    stroke_mat.parm("specular_roughness").set(0.5)

    # alphas are randomized depending on rand_id attribute created on strokes 
    tex1 = matnet.createNode("mtlximage", "brush_tex1")
    tex1.parm("file").set(brush1_path)
    tex2 = matnet.createNode("mtlximage", "brush_tex2")
    tex2.parm("file").set(brush2_path)

    geom_rand = matnet.createNode("mtlxgeompropvalue", "input_rand")
    geom_rand.parm("geomprop").set("rand_id")

    mult = matnet.createNode("mtlxmultiply", "mul_by_2")
    mult.setInput(0, geom_rand)
    mult.parm("in2").set(2)

    floor = matnet.createNode("mtlxfloor", "floor_bias")
    floor.setInput(0, mult)

    mix = matnet.createNode("mtlxmix", "mix_textures")
    mix.setInput(0, tex1)
    mix.setInput(1, tex2)
    mix.setInput(2, floor)  

    fit = matnet.createNode("mtlxrange", "fit_opacity") #looks better when more transparent
    fit.parm("outhigh_color3r").set(0.5)
    fit.parm("outhigh_color3g").set(0.5)
    fit.parm("outhigh_color3b").set(0.5)
    fit.setInput(0, mix)
    
    stroke_mat.setNamedInput("opacity", fit, 0)

    matnet.layoutChildren()

    return stroke_mat
    
   
    
    

################################################################    
################################################################    

if hasattr(hou.session, "stroke_ui"):
    try:
        hou.session.stroke_ui.ui_save_settings()  
        hou.session.stroke_ui.close()
    except:
        pass

hou.session.stroke_ui = StrokeToolUI()
hou.session.stroke_ui.show()

