#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Mar  8 10:58:19 2017

@author: steven
"""

import volmdlr as vm
import volmdlr.edges as edges

p1 = vm.Point2D(1,1.45)
p2 = vm.Point2D(0.4,0.1)
l1 = edges.Line2D(p1, p2)

p3 = vm.Point2D(-1,0)
p4 = vm.Point2D(1,-0.5)
l2 = edges.Line2D(p3, p4)

p5,bl1,bl2 = vm.Point2D.line_intersection(l1, l2,True)
p6 = vm.Point2D.middle_point(p1,p3)

p7 = vm.Point2D.line_projection(p6, l1)
p8 = vm.Point2D.line_projection(p6, l2)

c=vm.CompositePrimitive2D([l1, l2, p5, p6, p7 ,p8])
c.plot()
