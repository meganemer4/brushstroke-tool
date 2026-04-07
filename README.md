# brushstroke-tool
A Python script that generates brush stroke geometry and shaders for assets in Houdini
---

# Instructions
1. Download the script and at least 2 brush alphas (or use your own). 

2. Paste the contents of brush_strokes.py into a Python Shell or run it from a custom shelf tool.

3. Ensure that each asset has either a texture assigned (no more than 1 per asset), or a flat basecolor. To avoid potential issues, create simple materials for each asset that only have a basecolor texture. If no textures are present, brush strokes will use whatever color the basecolor is set to. 
 
4. Select one or more geometry nodes to generate brush strokes for, and run the script.

5. Select the appropriate settings in the UI menu. Keep in mind that density and stroke size can be adjusted on the subnet. 
  
6. Generate the strokes. This creates a subnet that has adjustable attributes on the node. Density and stroke size needs can vary drastically depending on the model. 

7. Render the new subnet.

Tips:
- While the script can be run on several objects at once, it is generally best to generate separate subnets for different groups of models for more control.
- This tool works best with simpler, organic models. Complex models can get messy and weird.
- Be sure to remove any roughness maps, normal maps, etc from the shaders before running the script. Otherwise, the strokes might be generated with the wrong texture. Simple shaders with a basecolor texture only are ideal for this. 
- After getting a desired result, it's best to cache the geo out for rendering, to avoid any accidental updates in the stroke generation.
- Both Karma and Mantra get similar visual results from this tool, but Mantra renders with this tool can be quite slow in comparison, especially when the density is high. Karma XPU worked the best for me.
- Houdini can be somewhat crashy while generating strokes on multiple assets at once, and sometimes crashes while deleting a brush stroke subnet
  
