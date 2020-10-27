#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

"""
import triangle
from typing import List
import math
import numpy as npy
import matplotlib.pyplot as plt
import dessia_common as dc
from geomdl import BSpline
import volmdlr
import volmdlr.wires

import volmdlr.primitives2d
import volmdlr.primitives3d

class Surface2D(volmdlr.core.Primitive2D):
    """
    A surface bounded by an outer contour
    """
    def __init__(self, outer_contour: volmdlr.wires.Contour2D,
                 inner_contours: List[volmdlr.wires.Contour2D],
                 name:str='name'):
        self.outer_contour = outer_contour
        self.inner_contours = inner_contours

        volmdlr.core.Primitive2D.__init__(self, name=name)

    def triangulation(self, min_x_density=None, min_y_density=None):
        outer_polygon = self.outer_contour.polygonization(min_x_density=15, min_y_density=12)
        # ax2 = outer_polygon.MPLPlot(color='r', point_numbering=True)
        points = outer_polygon.points
        vertices = [(p.x, p.y) for p in points]
        n = len(outer_polygon.points)
        segments = [(i, i+1) for i in range(n-1)]
        segments.append((n-1, 0))
        point_index = {p:i for i,p in enumerate(points)}
        holes = []

        for inner_contour in self.inner_contours:
            inner_polygon = inner_contour.polygonization()
            # inner_polygon.MPLPlot(ax=ax2)
            for point in inner_polygon.points:
                if not point in point_index:
                    points.append(point)
                    vertices.append((point.x, point.y))
                    point_index[point] = n
                    n += 1
            for point1, point2 in zip(inner_polygon.points[:-1],
                                      inner_polygon.points[1:]):
                segments.append((point_index[point1],
                                 point_index[point2]))
            segments.append((point_index[inner_polygon.points[-1]],
                             point_index[inner_polygon.points[0]]))
            rpi = inner_contour.random_point_inside()
            holes.append((rpi.x, rpi.y))


        tri = {'vertices': npy.array(vertices).reshape((-1, 2)),
               'segments': npy.array(segments).reshape((-1, 2)),
               }
        if holes:
            tri['holes'] = npy.array(holes).reshape((-1, 2))

        t = triangle.triangulate(tri, 'p')
        triangles = t['triangles'].tolist()

        return volmdlr.display.DisplayMesh2D(points, triangles=triangles, edges=None)

    def plot(self, ax=None):
        if ax is None:
            fig, ax = plt.subplots()
            ax.set_aspect('equal')
        self.outer_contour.MPLPlot(ax=ax)
        for inner_contour in self.inner_contours:
            inner_contour.MPLPlot(ax=ax)

        ax.set_aspect('equal')
        ax.margins(0.1)
        return ax


class Surface3D():
    """
    Abstract class
    """
    def face_from_contours3d(self, contours3d):
        contours2d = []
        max_area = 0.

        for ic, contour3d in contours3d:
            contour2d = self.contour3d_to_2d(contour3d)
            contour_area = contour2d.Area()
            if contour_area > max_area:
                max_area = contour_area
                outer_contour_index = ic
            contours2d.append(contour2d)

        outer_contour = contour2d[outer_contour_index]
        del contour2d[outer_contour_index]
        surface2d = (outer_contour, contours2d)

        self.SURFACE_TO_FACE[self.__class__](self, surface2d)

class Plane3D(Surface3D):
    def __init__(self, frame: volmdlr.Frame3D, name: str = ''):
        """
        :param frame: u and v of frame describe the plane, w is the normal
        """
        self.frame = frame
        self.name = name

    def __hash__(self):
        return hash(self.frame)

    def __eq__(self, other_plane):
        return (self.frame.origin == other_plane.frame.origin and \
                self.frame.w.is_colinear_to(other_plane.frame.w))

    def to_dict(self):
        # improve the object structure ?
        dict_ = dc.DessiaObject.base_dict(self)
        dict_['frame'] = self.frame.to_dict()
        dict_['name'] = self.name
        dict_['object_class'] = 'volmdlr.core.Plane3D'
        return dict_

    @classmethod
    def from_step(cls, arguments, object_dict):
        frame3d = object_dict[arguments[1]]

        return cls(frame3d, arguments[0][1:-1])

    @classmethod
    def from_3_points(cls, point1, point2, point3):
        """
        Point 1 is used as origin of the plane
        """
        vector1 = point2 - point1
        vector2 = point3 - point1
        vector1.normalize()
        vector2.normalize()
        normal = vector1.cross(vector2)
        normal.normalize()
        vector = normal.cross(vector1)
        frame = volmdlr.Frame3D(point1, vector1, normal.cross(vector1), normal)
        return cls(frame)

    @classmethod
    def from_normal(cls, point, normal):
        v1 = normal.deterministic_unit_normal_vector()
        v2 = v1.cross(normal)
        return cls(volmdlr.Frame3D(point, v1, v2, normal))

    @classmethod
    def from_points(cls, points):
        if len(points) < 3:
            raise ValueError
        elif len(points) == 3:
            return cls.from_3_points(volmdlr.Point3D(points[0].vector),
                                     volmdlr.Vector3D(points[1].vector),
                                     volmdlr.Vector3D(points[2].vector))
        else:
            points = [p.copy() for p in points]
            indexes_to_del = []
            for i, point in enumerate(points[1:]):
                if point == points[0]:
                    indexes_to_del.append(i)
            for index in indexes_to_del[::-1]:
                del points[index + 1]

            origin = volmdlr.Point3D(points[0].vector)
            vector1 = volmdlr.Vector3D(points[1] - origin)
            vector1.normalize()
            vector2_min = volmdlr.Vector3D(points[2] - origin)
            vector2_min.normalize()
            dot_min = abs(vector1.dot(vector2_min))
            for point in points[3:]:
                vector2 = volmdlr.Vector3D(point - origin)
                vector2.normalize()
                dot = abs(vector1.dot(vector2))
                if dot < dot_min:
                    vector2_min = vector2
                    dot_min = dot
            return cls.from_3_points(origin, vector1 + origin,
                                     vector2_min + origin)

    def point_on_plane(self, point):
        if math.isclose(self.frame.w.dot(point - self.frame.origin), 0,
                        abs_tol=1e-6):
            return True
        return False

    def line_intersections(self, line):
        u = line.points[1] - line.points[0]
        w = line.points[0] - self.frame.origin
        if math.isclose(self.frame.w.dot(u), 0, abs_tol=1e-08):
            return []
        intersection_abscissea = - self.frame.w.dot(w) / self.frame.w.dot(u)
        return [line.points[0] + intersection_abscissea * u]

    def linesegment_intersection(self, linesegment, abscissea=False):
        u = linesegment.points[1] - linesegment.points[0]
        w = linesegment.points[0] - self.frame.origin
        normaldotu = self.frame.w.dot(u)
        if math.isclose(normaldotu, 0, abs_tol=1e-08):
            if abscissea:
                return None, None
            return None
        intersection_abscissea = - self.frame.w.dot(w) / normaldotu
        if intersection_abscissea < 0 or intersection_abscissea > 1:
            if abscissea:
                return None, None
            return None
        if abscissea:
            return linesegment.points[
                       0] + intersection_abscissea * u, intersection_abscissea
        return linesegment.points[0] + intersection_abscissea * u

    def equation_coefficients(self):
        """
        returns the a,b,c,d coefficient from equation ax+by+cz+d = 0
        """
        a, b, c = self.frame.w
        d = -self.frame.origin.dot(self.frame.w)
        return (a, b, c, d)

    def plane_intersection(self, other_plane):
        line_direction = self.frame.w.cross(other_plane.frame.w)

        if line_direction.Norm() < 1e-6:
            return None

        a1, b1, c1, d1 = self.equation_coefficients()
        a2, b2, c2, d2 = other_plane.equation_coefficients()

        if a1 * b2 - a2 * b1 != 0.:
            x0 = (b1 * d2 - b2 * d1) / (a1 * b2 - a2 * b1)
            y0 = (a2 * d1 - a1 * d2) / (a1 * b2 - a2 * b1)
            point1 = volmdlr.Point3D((x0, y0, 0))
        else:
            y0 = (b2 * d2 - c2 * d1) / (b1 * c2 - c1 * b2)
            z0 = (c1 * d1 - b1 * d2) / (b1 * c2 - c1 * b2)
            point1 = volmdlr.Point3D((0, y0, z0))

        point2 = point1 + line_direction
        return volmdlr.Line3D(point1, point2)

    def rotation(self, center, axis, angle, copy=True):
        if copy:
            new_frame = self.frame.rotation(center, axis, angle, copy=True)
            return Plane3D(new_frame)
        else:
            self.frame.rotation(center, axis, angle, copy=False)

    def translation(self, offset, copy=True):
        if copy:
            new_frame = self.frame.translation(offset, True)
            return Plane3D(new_frame)
        else:
            self.origin.translation(offset, False)

    def frame_mapping(self, frame, side, copy=True):
        """
        side = 'old' or 'new'
        """
        if side == 'old':
            new_origin = frame.old_coordinates(self.frame.origin)
            new_vector1 = frame.Basis().old_coordinates(self.frame.u)
            new_vector2 = frame.Basis().old_coordinates(self.frame.v)
            new_vector3 = frame.Basis().old_coordinates(self.frame.w)
            if copy:
                return Plane3D(volmdlr.Frame3D(new_origin, new_vector1, new_vector2, new_vector3), self.name)
            else:
                # self.origin = new_origin
                # self.vectors = [new_vector1, new_vector2]
                # self.normal = frame.Basis().old_coordinates(self.normal)
                # self.normal.normalize()
                self.frame.origin = new_origin
                self.frame.u = new_vector1
                self.frame.v = new_vector2
                self.frame.w = new_vector3

        if side == 'new':
            new_origin = frame.new_coordinates(self.frame.origin)
            new_vector1 = frame.Basis().new_coordinates(self.frame.u)
            new_vector2 = frame.Basis().new_coordinates(self.frame.v)
            new_vector3 = frame.Basis().new_coordinates(self.frame.w)
            if copy:
                return Plane3D(volmdlr.Frame3D(new_origin, new_vector1, new_vector2, new_vector3), self.name)
            else:
                self.frame.origin = new_origin
                self.frame.u = new_vector1
                self.frame.v = new_vector2
                self.frame.w = new_vector3

    def copy(self):
        new_origin = self.origin.copy()
        new_vector1 = self.vectors[0].copy()
        new_vector2 = self.vectors[1].copy()
        return Plane3D(new_origin, new_vector1, new_vector2, self.name)

    def MPLPlot(self, ax=None):
        if ax is None:
            fig = plt.figure()
            ax = fig.add_subplot(111, projection='3d')
        else:
            fig = ax.figure

        self.origin.MPLPlot(ax)
        self.vectors[0].MPLPlot(ax, starting_point=self.origin, color='r')
        self.vectors[1].MPLPlot(ax, starting_point=self.origin, color='g')
        return ax

    def babylon_script(self):
        s = 'var myPlane = BABYLON.MeshBuilder.CreatePlane("myPlane", {width: 0.5, height: 0.5, sideOrientation: BABYLON.Mesh.DOUBLESIDE}, scene);\n'
        s += 'myPlane.setPositionWithLocalVector(new BABYLON.Vector3({},{},{}));\n'.format(
            self.origin[0], self.origin[1], self.origin[2])

        s += 'var axis1 = new BABYLON.Vector3({}, {}, {});\n'.format(
            self.vectors[0][0], self.vectors[0][1], self.vectors[0][2])
        s += 'var axis2 = new BABYLON.Vector3({}, {}, {});\n'.format(
            self.vectors[1][0], self.vectors[1][1], self.vectors[1][2])
        s += 'var axis3 = new BABYLON.Vector3({}, {}, {});\n'.format(
            self.normal[0], self.normal[1], self.normal[2])
        s += 'var orientation = BABYLON.Vector3.rotationFromAxis(axis1, axis2, axis3);\n'
        s += 'myPlane.rotation = orientation;\n'

        s += 'var planemat = new BABYLON.StandardMaterial("planemat", scene);\n'
        s += 'planemat.alpha = 0.4;\n'
        s += 'myPlane.material = planemat;\n'

        return s

    def point2d_to_3d(self, point2d):
        return point2d.to_3d(self.frame.origin, self.frame.u, self.frame.v)

    def point3d_to_2d(self, point3d):
        return point3d.to_2d(self.frame.origin, self.frame.u, self.frame.v)

    def contour2d_to_3d(self, contour2d):
        return contour2d.to_3d(self.frame.origin, self.frame.u, self.frame.v)

    def contour3d_to_2d(self, contour3d):
        return contour3d.to_2d(self.frame.origin, self.frame.u, self.frame.v)


    def rectangular_cut(self, x1:float, x2:float,
                        y1:float, y2:float, name:str=''):

        p1 = volmdlr.Point2D(x1, y1)
        p2 = volmdlr.Point2D(x2, y1)
        p3 = volmdlr.Point2D(x2, y2)
        p4 = volmdlr.Point2D(x1, y2)
        outer_contour = volmdlr.wires.Polygon2D([p1, p2, p3, p4])
        surface = Surface2D(outer_contour, [])
        return Face3D(self, surface, name)

PLANE3D_OXY = Plane3D(volmdlr.OXYZ)
PLANE3D_OYZ = Plane3D(volmdlr.OYZX)
PLANE3D_OZX = Plane3D(volmdlr.OZXY)

class CylindricalSurface3D(Surface3D):
    # face_class = CylindricalFace3D
    """
    :param frame: frame.w is axis, frame.u is theta=0 frame.v theta=pi/2
    :type frame: volmdlr.Frame3D
    :param radius: Cylinder's radius
    :type radius: float
    """

    def __init__(self, frame, radius, name=''):
        self.frame = frame
        self.radius = radius
        self.name = name

    def point2d_to_3d(self, point2d):
        p = volmdlr.Point3D(self.radius * math.cos(point2d[0]),
                            self.radius * math.sin(point2d[0]),
                            point2d[1])
        return self.frame.old_coordinates(p)

    def point3d_to_2d(self, point3d):
        u1, u2 = point3d.x / self.radius, point3d.y / self.radius
        theta = volmdlr.sin_cos_angle(u1, u2)
        return volmdlr.Point2D(theta, point3d.z)

    @classmethod
    def from_step(cls, arguments, object_dict):
        frame3d = object_dict[arguments[1]]
        U, W = frame3d.v, -frame3d.u
        U.normalize()
        W.normalize()
        V = W.cross(U)
        frame_direct = volmdlr.Frame3D(frame3d.origin, U, V, W)
        radius = float(arguments[2]) / 1000
        return cls(frame_direct, radius, arguments[0][1:-1])

    def frame_mapping(self, frame, side, copy=True):
        basis = frame.Basis()
        if side == 'new':
            new_origin = frame.new_coordinates(self.frame.origin)
            new_u = basis.new_coordinates(self.frame.u)
            new_v = basis.new_coordinates(self.frame.v)
            new_w = basis.new_coordinates(self.frame.w)
            new_frame = volmdlr.Frame3D(new_origin, new_u, new_v, new_w)
            if copy:
                return CylindricalSurface3D(new_frame, self.radius,
                                            name=self.name)
            else:
                self.frame = new_frame

        if side == 'old':
            new_origin = frame.old_coordinates(self.frame.origin)
            new_u = basis.old_coordinates(self.frame.u)
            new_v = basis.old_coordinates(self.frame.v)
            new_w = basis.old_coordinates(self.frame.w)
            new_frame = volmdlr.Frame3D(new_origin, new_u, new_v, new_w)
            if copy:
                return CylindricalSurface3D(new_frame, self.radius,
                                            name=self.name)
            else:
                self.frame = new_frame

    def rectangular_cut(self, theta1:float, theta2:float,
                        z1:float, z2:float, name:str=''):

        if theta1 == theta2:
            theta2 += volmdlr.volmdlr.TWO_PI

        p1 = volmdlr.Point2D(theta1, z1)
        p2 = volmdlr.Point2D(theta2, z1)
        p3 = volmdlr.Point2D(theta2, z2)
        p4 = volmdlr.Point2D(theta1, z2)
        outer_contour = volmdlr.wires.Polygon2D([p1, p2, p3, p4])
        surface2d = Surface2D(outer_contour, [])
        return volmdlr.faces.CylindricalFace3D(self, surface2d, name)


class ToroidalSurface3D(Surface3D):
    # face_class = volmdlr.faces3d.ToroidalFace3D
    """
    :param frame: Tore's frame: origin is thet center, u is pointing at
                    theta=0
    :type frame: volmdlr.Frame3D
    :param R: Tore's radius
    :type R: float
    :param r: Circle to revolute radius
    :type r: float
    Definitions of R and r according to https://en.wikipedia.org/wiki/Torus
    """

    def __init__(self, frame: volmdlr.Frame3D,
                 R: float, r: float, name: str = ''):
        self.frame = frame
        self.R = R
        self.r = r
        self.name = name
        self.frame = frame

    def _bounding_box(self):
        d = self.R + self.r
        p1 = self.frame.origin + self.frame.u * d + self.frame.v * d + self.frame.w * self.r
        p2 = self.frame.origin + self.frame.u * d + self.frame.v * d - self.frame.w * self.r
        p3 = self.frame.origin + self.frame.u * d - self.frame.v * d + self.frame.w * self.r
        p4 = self.frame.origin + self.frame.u * d - self.frame.v * d - self.frame.w * self.r
        p5 = self.frame.origin - self.frame.u * d + self.frame.v * d + self.frame.w * self.r
        p6 = self.frame.origin - self.frame.u * d + self.frame.v * d - self.frame.w * self.r
        p7 = self.frame.origin - self.frame.u * d - self.frame.v * d + self.frame.w * self.r
        p8 = self.frame.origin - self.frame.u * d - self.frame.v * d - self.frame.w * self.r

        return volmdlr.core.BoundingBox.from_points([p1, p2, p3, p4, p5, p6, p7, p8])

    def point2d_to_3d(self, point2d):
        theta, phi = point2d
        x = (self.R + self.r * math.cos(phi)) * math.cos(theta)
        y = (self.R + self.r * math.cos(phi)) * math.sin(theta)
        z = self.r * math.sin(phi)
        return self.frame.old_coordinates(volmdlr.Point3D(x, y, z))

    def point3d_to_2d(self, point3d):
        # points_2D = []
        x, y, z = point3d
        if z < -self.r:
            z = -self.r
        elif z > self.r:
            z = self.r

        zr = z / self.r
        phi = math.asin(zr)

        u = self.R + math.sqrt((self.r ** 2) - (z ** 2))
        u1, u2 = round(x / u, 5), round(y / u, 5)
        theta = volmdlr.sin_cos_angle(u1, u2)

        return volmdlr.volmdlr.Point2D(theta, phi)

    @classmethod
    def from_step(cls, arguments, object_dict):
        frame3d = object_dict[arguments[1]]
        U, W = frame3d.v, -frame3d.u
        U.normalize()
        W.normalize()
        V = W.cross(U)
        frame_direct = volmdlr.Frame3D(frame3d.origin, U, V, W)
        rcenter = float(arguments[2]) / 1000
        rcircle = float(arguments[3]) / 1000
        return cls(frame_direct, rcenter, rcircle, arguments[0][1:-1])

    def frame_mapping(self, frame, side, copy=True):
        basis = frame.Basis()
        if side == 'new':
            new_origin = frame.new_coordinates(self.frame.origin)
            new_u = basis.new_coordinates(self.frame.u)
            new_v = basis.new_coordinates(self.frame.v)
            new_w = basis.new_coordinates(self.frame.w)
            new_frame = volmdlr.Frame3D(new_origin, new_u, new_v, new_w)
            if copy:
                return ToroidalSurface3D(new_frame,
                                         self.R, self.r,
                                         name=self.name)
            else:
                self.frame = new_frame

        if side == 'old':
            new_origin = frame.old_coordinates(self.frame.origin)
            new_u = basis.old_coordinates(self.frame.u)
            new_v = basis.old_coordinates(self.frame.v)
            new_w = basis.old_coordinates(self.frame.w)
            new_frame = volmdlr.Frame3D(new_origin, new_u, new_v, new_w)
            if copy:
                return ToroidalSurface3D(new_frame,
                                         self.R, self.r,
                                         name=self.name)
            else:
                self.frame = new_frame

    def rectangular_cut(self, theta1, theta2, phi1, phi2, name=''):
        # theta1 = angle_principal_measure(theta1)
        # theta2 = angle_principal_measure(theta2)
        # phi1 = angle_principal_measure(phi1)
        # phi2 = angle_principal_measure(phi2)

        if phi1 == phi2:
            phi2 += volmdlr.TWO_PI
        elif phi2 < phi1:
            phi2 += volmdlr.TWO_PI
        if theta1 == theta2:
            theta2 += volmdlr.TWO_PI
        elif theta2 < theta1:
            theta2 += volmdlr.TWO_PI

        p1 = volmdlr.Point2D(theta1, phi1)
        p2 = volmdlr.Point2D(theta1, phi2)
        p3 = volmdlr.Point2D(theta2, phi2)
        p4 = volmdlr.Point2D(theta2, phi1)
        outer_contour = volmdlr.wires.Polygon2D([p1, p2, p3, p4])
        return ToroidalFace3D(self,
                              Surface2D(outer_contour, []),
                              name)

    def contour2d_to_3d(self, contour2d):
        edges3d = []
        # contour2d.MPLPlot()
        for edge in contour2d.primitives:
            if isinstance(edge, volmdlr.volmdlr.LineSegment2D):
                if (edge.points[0][0] == edge.points[1][0]) \
                        or (edge.points[0][1] == edge.points[1][1]):
                    # Y progression: it's an arc
                    edges3d.append(volmdlr.Arc3D(self.point2d_to_3d(edge.points[0]),
                                         self.point2d_to_3d(
                                             0.5 * (edge.points[0] \
                                                    + edge.points[1])),
                                         self.point2d_to_3d(edge.points[1])))
                else:
                    edges3d.append(volmdlr.Arc3D(self.point2d_to_3d(edge.points[0]),
                                         self.point2d_to_3d(
                                             0.5 * (edge.points[0] \
                                                    + edge.points[1])),
                                         self.point2d_to_3d(edge.points[1])))
            else:
                raise NotImplementedError(
                    'The primitive {} is not supported in 2D->3D'.format(edge))

        return volmdlr.Contour3D(edges3d)

    def contour3d_to_2d(self, contour3d, toroidalsurface3d):
        frame = toroidalsurface3d.frame
        n = frame.w
        # center = frame.origin
        rcenter, rcircle = toroidalsurface3d.rcenter, toroidalsurface3d.rcircle

        primitives, start_end, all_points = [], [], []
        for edge in contour3d.edges:
            new_points = [frame.new_coordinates(pt) for pt in edge.points]
            if edge.__class__ is volmdlr.Arc3D:
                if edge.normal == n or edge.normal == -n:
                    start2d, end2d = self.points3d_to2d(new_points,
                                                        rcenter,
                                                        rcircle)

                    angle2d = abs(end2d[0] - start2d[0])
                    if math.isclose(edge.angle, volmdlr.TWO_PI, abs_tol=1e-6):
                        if start2d == end2d:
                            if math.isclose(start2d.vector[0], volmdlr.TWO_PI,
                                            abs_tol=1e-6):
                                end2d = end2d - volmdlr.volmdlr.Point2D((volmdlr.TWO_PI, 0))
                            else:
                                end2d = end2d + volmdlr.volmdlr.Point2D((volmdlr.TWO_PI, 0))
                    elif not (math.isclose(edge.angle, angle2d, abs_tol=1e-2)):
                        # if math.isclose(angle2d, volmdlr.TWO_PI, abs_tol=1e-2) :
                        if start2d[0] < end2d[0]:
                            end2d = start2d + volmdlr.volmdlr.Point2D((edge.angle, 0))
                        else:
                            end2d = start2d - volmdlr.volmdlr.Point2D((edge.angle, 0))
                    #####################

                    ls_toadd = volmdlr.volmdlr.LineSegment2D(start2d, end2d)
                    same = volmdlr.faces3d.volmdlr.faces3d.Face3D.LS2D_inprimitives(ls_toadd, primitives)
                    if same is False:
                        primitives.append([ls_toadd])
                        all_points.extend(ls_toadd.points)
                        start_end.append(ls_toadd.points)

                else:
                    points2d = self.points3d_to2d(new_points,
                                                  rcenter, rcircle)
                    lines = []
                    for k in range(0, len(points2d) - 1):
                        lines.append(
                            volmdlr.LineSegment2D(points2d[k], points2d[k + 1]))
                    points, prim_list = [], []
                    for ls_toadd in lines:
                        same = volmdlr.faces3d.Face3D.LS2D_inprimitives(ls_toadd, primitives)
                        if same is False:
                            prim_list.append(ls_toadd)
                            points.extend(ls_toadd.points)
                    if len(points) > 0:
                        all_points.extend(points)
                        primitives.append(prim_list)
                        start_end.append([points[0], points[-1]])

            elif edge.__class__ is volmdlr.LineSegment3D:
                start2d, end2d = self.points3d_to2d(new_points,
                                                              rcenter, rcircle)
                ls_toadd = volmdlr.LineSegment2D(start2d, end2d)
                same = volmdlr.faces3d.Face3D.LS2D_inprimitives(ls_toadd, primitives)
                if same is False:
                    primitives.append([ls_toadd])
                    all_points.extend(ls_toadd.points)
                    start_end.append(ls_toadd.points)

            else:
                points2d = volmdlr.faces3d.volmdlr.points3d_to2d(new_points, rcenter,
                                                        rcircle)
                lines = []
                for k in range(0, len(points2d) - 1):
                    lines.append(volmdlr.LineSegment2D(points2d[k], points2d[k + 1]))
                points, prim_list = [], []
                for ls_toadd in lines:
                    same = volmdlr.faces3d.Face3D.LS2D_inprimitives(ls_toadd, primitives)
                    if same is False:
                        prim_list.append(ls_toadd)
                        points.extend(ls_toadd.points)
                if len(points) > 0:
                    all_points.extend(points)
                    primitives.append(prim_list)
                    start_end.append([points[0], points[-1]])

        points_se, primitives_se = [], []
        for double in start_end:
            primitives_se.append(volmdlr.LineSegment2D(double[0], double[1]))
            points_se.extend(double)
        poly_se = volmdlr.Polygon2D(points_se)

        xmax, xmin = max(pt[0] for pt in points_se), min(
            pt[0] for pt in points_se)
        ymax, ymin = max(pt[1] for pt in points_se), min(
            pt[1] for pt in points_se)
        pt1, pt2, pt3, pt4 = volmdlr.volmdlr.Point2D((xmin, ymin)), volmdlr.volmdlr.Point2D(
            (xmin, ymax)), volmdlr.volmdlr.Point2D((xmax, ymin)), volmdlr.volmdlr.Point2D((xmax, ymax))
        diag1, diag2 = volmdlr.LineSegment2D(pt1, pt4), volmdlr.LineSegment2D(pt2, pt3)
        diag1_cut, diag2_cut = [], []
        diag1_pointcut, diag2_pointcut = [], []
        for enum, l in enumerate(primitives_se):
            cut1 = diag1.line_intersections(l)
            cut2 = diag2.line_intersections(l)
            if cut1 is not None:
                diag1_cut.append(enum)
                diag1_pointcut.append(cut1)
            if cut2 is not None:
                diag2_cut.append(enum)
                diag2_pointcut.append(cut2)

        points_common = []
        for enum1, pos1 in enumerate(diag1_cut):
            for enum2, pos2 in enumerate(diag2_cut):
                if pos1 == pos2:
                    points_common.append(primitives_se[pos1].points)

        if len(points_common) >= 1:
            solve = False
            for couple in points_common:
                if solve:
                    break
                check1, check2 = poly_se.PointBelongs(
                    couple[0]), poly_se.PointBelongs(couple[1])
                start, end = couple[0].vector[0], couple[1].vector[0]
                if math.isclose(start, end, abs_tol=5e-2):
                    intersect = min(start, end)
                    if math.isclose(intersect, math.pi, abs_tol=5e-2):
                        # all_points = check_singularity(all_points)
                        # intersect = 0

                        ##################### NEW
                        points_sing = volmdlr.check_singularity(all_points)
                        pt0, pt2pi = 0, 0
                        for pt in points_sing:
                            if math.isclose(pt.vector[0], 0, abs_tol=1e-2):
                                pt0 += 1
                            elif math.isclose(pt.vector[0], volmdlr.TWO_PI,
                                              abs_tol=1e-2):
                                pt2pi += 1
                        points_sing.sort(key=lambda pt: pt[1])
                        points_sing.sort(key=lambda pt: pt[0])
                        if pt2pi != 0 and pt0 == 0:
                            points = [pt.copy() for pt in points_sing[::-1]]
                            points_sing = points
                        points_range = volmdlr.faces3d.Face3D.range_closest(points_sing)
                        all_points = volmdlr.delete_double_point(points_range)
                        break
                        #######################

                    # if math.isclose(intersect, 0, abs_tol = 1e-6) or math.isclose(intersect, volmdlr.TWO_PI, abs_tol = 1e-6) or (not check1 or not check2):
                    elif math.isclose(intersect, 0,
                                      abs_tol=1e-6) or math.isclose(intersect,
                                                                    volmdlr.TWO_PI,
                                                                    abs_tol=1e-6) or (
                            not check1 or not check2):
                        all_points = volmdlr.check_singularity(all_points)

                        points_cleaned = volmdlr.delete_double_point(all_points)
                        all_points = [pt.copy() for pt in points_cleaned]
                        all_points.sort(key=lambda pt: pt[0])
                        d1, d2 = (all_points[0] - all_points[-1]).Norm(), (
                                    all_points[0] - all_points[-2]).Norm()
                        if d2 < d1:
                            last = all_points[-1].copy()
                            all_points[-1] = all_points[-2].copy()
                            all_points[-2] = last
                        break
                    else:
                        points = []
                        for list_prim in primitives:
                            for k, prim in enumerate(list_prim):
                                new_list_points = []
                                change = 0
                                for pt in prim.points:
                                    if pt[0] < intersect:
                                        change += 1
                                        if math.isclose(pt[0], 0,
                                                        abs_tol=1e-1):
                                            new_list_points.append(volmdlr.volmdlr.Point2D((
                                                                           intersect + volmdlr.TWO_PI,
                                                                           pt[
                                                                               1])))
                                        else:
                                            new_list_points.append(volmdlr.volmdlr.Point2D(
                                                (volmdlr.TWO_PI + pt[0], pt[1])))
                                    elif math.isclose(pt[0], intersect,
                                                      abs_tol=1e-1):
                                        change += 1
                                        new_list_points.append(volmdlr.volmdlr.Point2D(
                                            (volmdlr.TWO_PI + pt[0], pt[1])))
                                    else:
                                        new_list_points.append(pt)
                                if change > 0:
                                    points.extend(new_list_points)
                                    # list_prim[k] = volmdlr.LineSegment2D(new_list_points[0], new_list_points[1])
                                else:
                                    points.extend(prim.points)
                                    continue
                        points_cleaned = volmdlr.delete_double_point(points)
                        all_points = volmdlr.faces3d.Face3D.range_trigo(points_cleaned)
                    solve = True
                else:
                    points_cleaned = volmdlr.delete_double_point(all_points)
                    all_points = [pt.copy() for pt in points_cleaned]
                    all_points.sort(key=lambda pt: pt[0])
                    d1, d2 = (all_points[0] - all_points[-1]).Norm(), (
                                all_points[0] - all_points[-2]).Norm()
                    if d2 < d1:
                        last = all_points[-1].copy()
                        all_points[-1] = all_points[-2].copy()
                        all_points[-2] = last
        else:
            points_cleaned = volmdlr.delete_double_point(all_points)
            all_points = [pt.copy() for pt in points_cleaned]
            all_points.sort(key=lambda pt: pt[0])
            d1, d2 = (all_points[0] - all_points[-1]).Norm(), (
                        all_points[0] - all_points[-2]).Norm()
            if d2 < d1:
                last = all_points[-1].copy()
                all_points[-1] = all_points[-2].copy()
                all_points[-2] = last

        primitives = volmdlr.faces3d.Face3D.create_primitives(all_points)

        # fig, ax = plt.subplots()
        # [pt.MPLPlot(ax=ax, color='g') for pt in all_points]
        # all_points[0].MPLPlot(ax=ax, color='m')
        # all_points[1].MPLPlot(ax=ax, color='r')
        # all_points[-1].MPLPlot(ax=ax)
        # all_points[-2].MPLPlot(ax=ax, color='b')
        # [p.MPLPlot(ax=ax) for p in primitives]

        l_vert = volmdlr.LineSegment2D((pt2 + pt4) / 2, (pt1 + pt3) / 2)
        solve = False
        for prim in primitives:
            if solve:
                break
            intersect = prim.line_intersections(l_vert)
            if intersect is not None:
                x_intersect = intersect.vector[0]
                y_intersect = intersect.vector[1]
                value1, value2 = ymax - 0.2 * (ymax - ymin), ymin + 0.2 * (
                            ymax - ymin)
                if y_intersect < max(value1, value2) and y_intersect > min(
                        value1, value2):
                    points = []
                    for k, prim in enumerate(primitives):
                        new_list_points, change = [], 0
                        for pt in prim.points:
                            if pt[0] < x_intersect:
                                change += 1
                                if math.isclose(pt[0], 0, abs_tol=1e-1):
                                    new_list_points.append(volmdlr.volmdlr.Point2D(
                                        (x_intersect + volmdlr.TWO_PI, pt[1])))
                                else:
                                    new_list_points.append(
                                        volmdlr.volmdlr.Point2D((volmdlr.TWO_PI + pt[0], pt[1])))
                            else:
                                new_list_points.append(pt)
                        if change > 0:
                            points.extend(new_list_points)
                            primitives[k] = volmdlr.LineSegment2D(new_list_points[0],
                                                          new_list_points[1])
                        else:
                            points.extend(prim.points)
                            continue
                    solve = True
                    points_cleaned = volmdlr.delete_double_point(points)
                    all_points = volmdlr.faces3d.Face3D.range_trigo(points_cleaned)
                    primitives = volmdlr.faces3d.Face3D.create_primitives(all_points)

        contour2d = [volmdlr.Contour2D(primitives)]
        return contour2d


class ConicalSurface3D(Surface3D):
    # face_class = volmdlr.faces3d.ConicalFace3D
    """
    :param frame: Cone's frame to position it: frame.w is axis of cone
    :type frame: volmdlr.Frame3D
    :param r: Cone's bottom radius
    :type r: float
    :param semi_angle: Cone's semi-angle
    :type semi_angle: float
    """

    def __init__(self, frame, semi_angle, name=''):
        self.frame = frame
        self.semi_angle = semi_angle
        self.name = name

    @classmethod
    def from_step(cls, arguments, object_dict):
        frame3d = object_dict[arguments[1]]
        U, W = frame3d.v, frame3d.u
        U.normalize()
        W.normalize()
        V = W.cross(U)
        frame_direct = volmdlr.Frame3D(frame3d.origin, U, V, W)
        semi_angle = float(arguments[3])
        return cls(frame_direct, semi_angle, arguments[0][1:-1])

    def frame_mapping(self, frame, side, copy=True):
        basis = frame.Basis()
        if side == 'new':
            new_origin = frame.new_coordinates(self.frame.origin)
            new_u = basis.new_coordinates(self.frame.u)
            new_v = basis.new_coordinates(self.frame.v)
            new_w = basis.new_coordinates(self.frame.w)
            new_frame = volmdlr.Frame3D(new_origin, new_u, new_v, new_w)
            if copy:
                return ConicalSurface3D(new_frame, self.radius, name=self.name)
            else:
                self.frame = new_frame

        if side == 'old':
            new_origin = frame.old_coordinates(self.frame.origin)
            new_u = basis.old_coordinates(self.frame.u)
            new_v = basis.old_coordinates(self.frame.v)
            new_w = basis.old_coordinates(self.frame.w)
            new_frame = volmdlr.Frame3D(new_origin, new_u, new_v, new_w)
            if copy:
                return ConicalSurface3D(new_frame, self.radius, name=self.name)
            else:
                self.frame = new_frame

    def point2d_to_3d(self, point):
        theta, z = point
        new_point = volmdlr.Point3D((z * self.semi_angle * math.cos(theta),
                             z * self.semi_angle * math.sin(theta),
                             z,
                             ))
        return self.frame.old_coordinates(new_point)

    def point3d_to_2d(self, point):
        z = self.frame.w.dot(point)
        x, y = point.PlaneProjection(self.frame.origin, self.frame.u,
                                     self.frame.v)
        theta = math.atan2(y, x)
        return volmdlr.volmdlr.Point2D([theta, z])

    def rectangular_cut(self, theta1: float, theta2: float,
                        z1: float, z2: float, name: str=''):
        # theta1 = angle_principal_measure(theta1)
        # theta2 = angle_principal_measure(theta2)
        if theta1 == theta2:
            theta2 += volmdlr.TWO_PI

        p1 = volmdlr.volmdlr.Point2D((theta1, z1))
        p2 = volmdlr.volmdlr.Point2D((theta2, z1))
        p3 = volmdlr.volmdlr.Point2D((theta2, z2))
        p4 = volmdlr.volmdlr.Point2D((theta1, z2))
        outer_contour = volmdlr.Polygon2D([p1, p2, p3, p4])
        return ConicalFace3D(self, outer_contour, [], name)


class SphericalSurface3D(Surface3D):
    # face_class = volmdlr.faces3d.SphericalFace3D
    """
    :param frame: Sphere's frame to position it
    :type frame: volmdlr.Frame3D
    :param radius: Sphere's radius
    :type radius: float
    """

    def __init__(self, frame, radius, name=''):
        self.frame = frame
        self.radius = radius
        self.name = name
        V = frame.v
        V.normalize()
        W = frame.w
        W.normalize()
        self.plane = Plane3D(frame.origin, V, W)

    @classmethod
    def from_step(cls, arguments, object_dict):
        frame3d = object_dict[arguments[1]]
        U, W = frame3d.v, frame3d.u
        U.normalize()
        W.normalize()
        V = W.cross(U)
        frame_direct = volmdlr.Frame3D(frame3d.origin, U, V, W)
        radius = float(arguments[2]) / 1000
        return cls(frame_direct, radius, arguments[0][1:-1])


    def point2d_to3d(self, point2d):
        # source mathcurve.com/surfaces/sphere
        # -pi<theta<pi, -pi/2<phi<pi/2
        theta, phi = point2d
        x = self.radius * math.cos(phi) * math.cos(theta)
        y = self.radius * math.cos(phi) * math.sin(theta)
        z = self.radius * math.sin(phi)
        return self.frame3d.old_coordinates(volmdlr.Point3D([x, y, z]))

    def point3d_to2d(self, point3d):
        x, y, z = point3d
        if z < -self.radius:
            z = -self.radius
        elif z > self.radius:
            z = self.radius

        zr = z / self.radius
        phi = math.asin(zr)

        u = math.sqrt((self.radius ** 2) - (z ** 2))
        if u == 0:
            u1, u2 = x, y
        else:
            u1, u2 = round(x / u, 5), round(y / u, 5)
        theta = volmdlr.sin_cos_angle(u1, u2)
        return volmdlr.volmdlr.Point2D((theta, phi))

class RuledSurface3D(Surface3D):
    # face_class = CylindricalFace3D
    """
    :param frame: frame.w is axis, frame.u is theta=0 frame.v theta=pi/2
    :type frame: volmdlr.Frame3D
    :param radius: Cylinder's radius
    :type radius: float
    """

    def __init__(self,
                 wire1:volmdlr.wires.Wire3D,
                 wire2:volmdlr.wires.Wire3D,
                 name=''):

        self.wire1 = wire1
        self.wire2 = wire2
        self.length1 = wire1.length()
        self.length2 = wire2.length()
        self.name = name

    def point2d_to_3d(self, point2d):
        x, y = point2d
        point1 = self.wire1.point_at_abscissa(x*self.length1)
        point2 = self.wire2.point_at_abscissa(x*self.length2)
        joining_line = volmdlr.edges.LineSegment3D(point1, point2)
        point = joining_line.point_at_abscissa(y*joining_line.length())
        return point

    def point3d_to_2d(self, point3d):
        raise NotImplementedError

    def rectangular_cut(self, x1: float, x2: float,
                        y1: float, y2: float, name: str=''):

        p1 = volmdlr.Point2D(x1, y1)
        p2 = volmdlr.Point2D(x2, y1)
        p3 = volmdlr.Point2D(x2, y2)
        p4 = volmdlr.Point2D(x1, y2)
        outer_contour = volmdlr.wires.Polygon2D([p1, p2, p3, p4])
        surface2d = Surface2D(outer_contour, [])
        return volmdlr.faces.RuledFace3D(self, surface2d, name)

class BSplineSurface3D(Surface3D):
    def __init__(self, degree_u, degree_v, control_points, nb_u, nb_v,
                 u_multiplicities, v_multiplicities, u_knots, v_knots,
                 weights=None, name=''):
        volmdlr.Primitive3D.__init__(self, basis_primitives=control_points, name=name)
        self.control_points = control_points
        self.degree_u = degree_u
        self.degree_v = degree_v
        self.nb_u = nb_u
        self.nb_v = nb_v
        u_knots = standardize_knot_vector(u_knots)
        v_knots = standardize_knot_vector(v_knots)
        self.u_knots = u_knots
        self.v_knots = v_knots
        self.u_multiplicities = u_multiplicities
        self.v_multiplicities = v_multiplicities
        self.weights = weights

        self.control_points_table = []
        points_row = []
        i = 1
        for pt in control_points:
            points_row.append(pt)
            if i == nb_v:
                self.control_points_table.append(points_row)
                points_row = []
                i = 1
            else:
                i += 1
        surface = BSpline.Surface()
        surface.degree_u = degree_u
        surface.degree_v = degree_v
        if weights is None:
            P = [(control_points[i][0], control_points[i][1],
                  control_points[i][2]) for i in range(len(control_points))]
            surface.set_ctrlpts(P, nb_u, nb_v)
        else:
            Pw = [(control_points[i][0] * weights[i],
                   control_points[i][1] * weights[i],
                   control_points[i][2] * weights[i],
                   weights[i]) for i in range(len(control_points))]
            surface.set_ctrlpts(Pw, nb_u, nb_v)
        knot_vector_u = []
        for i, u_knot in enumerate(u_knots):
            knot_vector_u.extend([u_knot] * u_multiplicities[i])
        knot_vector_v = []
        for i, v_knot in enumerate(v_knots):
            knot_vector_v.extend([v_knot] * v_multiplicities[i])
        surface.knotvector_u = knot_vector_u
        surface.knotvector_v = knot_vector_v
        surface.delta = 0.05
        surface_points = surface.evalpts

        self.surface = surface
        self.points = [volmdlr.Point3D((p[0], p[1], p[2])) for p in surface_points]

    def FreeCADExport(self, ip, ndigits=3):
        name = 'primitive{}'.format(ip)
        script = ""
        points = '['
        for i, pts_row in enumerate(self.control_points_table):
            pts = '['
            for j, pt in enumerate(pts_row):
                point = 'fc.Vector({},{},{}),'.format(pt[0], pt[1], pt[2])
                pts += point
            pts = pts[:-1] + '],'
            points += pts
        points = points[:-1] + ']'

        script += '{} = Part.BSplineSurface()\n'.format(name)
        if self.weights is None:
            script += '{}.buildFromPolesMultsKnots({},{},{},udegree={},vdegree={},uknots={},vknots={})\n'.format(
                name, points, self.u_multiplicities, self.v_multiplicities,
                self.degree_u, self.degree_v, self.u_knots, self.v_knots)
        else:
            script += '{}.buildFromPolesMultsKnots({},{},{},udegree={},vdegree={},uknots={},vknots={},weights={})\n'.format(
                name, points, self.u_multiplicities, self.v_multiplicities,
                self.degree_u, self.degree_v, self.u_knots, self.v_knots,
                self.weights)

        return script

    def rotation(self, center, axis, angle, copy=True):
        new_control_points = [p.rotation(center, axis, angle, True) for p in
                              self.control_points]
        new_BSplineSurface3D = BSplineSurface3D(self.degree_u, self.degree_v,
                                                new_control_points, self.nb_u,
                                                self.nb_v,
                                                self.u_multiplicities,
                                                self.v_multiplicities,
                                                self.u_knots, self.v_knots,
                                                self.weights, self.name)
        if copy:
            return new_BSplineSurface3D
        else:
            self.control_points = new_control_points
            self.curve = new_BSplineSurface3D.curve
            self.points = new_BSplineSurface3D.points

    def translation(self, offset, copy=True):
        new_control_points = [p.translation(offset, True) for p in
                              self.control_points]
        new_BSplineSurface3D = BSplineSurface3D(self.degree_u, self.degree_v,
                                                new_control_points, self.nb_u,
                                                self.nb_v,
                                                self.u_multiplicities,
                                                self.v_multiplicities,
                                                self.u_knots, self.v_knots,
                                                self.weights, self.name)
        if copy:
            return new_BSplineSurface3D
        else:
            self.control_points = new_control_points
            self.curve = new_BSplineSurface3D.curve
            self.points = new_BSplineSurface3D.points

    @classmethod
    def from_step(cls, arguments, object_dict):
        name = arguments[0][1:-1]

        degree_u = int(arguments[1])
        degree_v = int(arguments[2])
        points_sets = arguments[3][1:-1].split("),")
        points_sets = [elem + ")" for elem in points_sets[:-1]] + [
            points_sets[-1]]
        control_points = []
        for points_set in points_sets:
            points = [object_dict[int(i[1:])] for i in
                      points_set[1:-1].split(",")]
            nb_v = len(points)
            control_points.extend(points)
        nb_u = int(len(control_points) / nb_v)
        surface_form = arguments[4]
        if arguments[5] == '.F.':
            u_closed = False
        elif arguments[5] == '.T.':
            u_closed = True
        else:
            raise ValueError
        if arguments[6] == '.F.':
            v_closed = False
        elif arguments[6] == '.T.':
            v_closed = True
        else:
            raise ValueError
        self_intersect = arguments[7]
        u_multiplicities = [int(i) for i in arguments[8][1:-1].split(",")]
        v_multiplicities = [int(i) for i in arguments[9][1:-1].split(",")]
        u_knots = [float(i) for i in arguments[10][1:-1].split(",")]
        v_knots = [float(i) for i in arguments[11][1:-1].split(",")]
        knot_spec = arguments[12]

        if 13 in range(len(arguments)):
            weight_data = [float(i) for i in
                           arguments[13][1:-1].replace("(", "").replace(")",
                                                                        "").split(
                               ",")]
        else:
            weight_data = None

        return cls(degree_u, degree_v, control_points, nb_u, nb_v,
                   u_multiplicities, v_multiplicities, u_knots, v_knots,
                   weight_data, name)

class Face3D(volmdlr.core.Primitive3D):
    min_x_density=1
    min_y_density=1

    def __init__(self, surface3d, surface2d: Surface2D,
                 name: str = ''):
        self.surface3d = surface3d
        self.surface2d = surface2d

        self.bounding_box = self._bounding_box()

        volmdlr.core.Primitive3D.__init__(self, name=name)

    def __hash__(self):
        return hash(self.surface3d) + hash(self.surface2d)

    def __eq__(self, other_):
        equal = (self.surface3d == other_.surface3d
                 and self.surface2d == other_.surface2d)
        return equal

    @property
    def outer_contour3d(self):
        """

        """
        if self.surface2d.outer_contour.__class__.__name__ == 'Circle2D':
            return volmdlr.wires.Circle3D.from_3_points(
                self.surface3d.point2d_to_3d(
                    self.surface2d.outer_contour.point_at_abscissa(0.)),
                self.surface3d.point2d_to_3d(
                    self.surface2d.outer_contour.point_at_abscissa(
                        self.surface2d.outer_contour.radius)),
                self.surface3d.point2d_to_3d(
                    self.surface2d.outer_contour.point_at_abscissa(
                        2 * self.surface2d.outer_contour.radius)),
            )

        primitives3d = []
        for primitive2d in self.surface2d.outer_contour.primitives:
            if primitive2d.__class__ == volmdlr.edges.LineSegment2D:
                p1 = self.surface3d.point2d_to_3d(primitive2d.start)
                p2 = self.surface3d.point2d_to_3d(primitive2d.end)
                primitive3d = volmdlr.edges.LineSegment3D(p1, p2)
            elif primitive2d.__class__ == volmdlr.edges.Arc2D:
                start = self.surface3d.point2d_to_3d(primitive2d.start)
                interior = self.surface3d.point2d_to_3d(primitive2d.interior)
                end = self.surface3d.point2d_to_3d(primitive2d.end)
                primitive3d = volmdlr.edges.Arc3D(start, interior, end)
            else:
                print(self.surface2d.outer_contour.primitives)
                raise NotImplementedError('Unsupported primitive {}' \
                                          .format(
                    primitive2d.__class__.__name__))

            primitives3d.append(primitive3d)
        return volmdlr.wires.Contour3D(primitives3d)

    def _bounding_box(self):
        """
        Flawed method, to be enforced by overloading
        """
        return self.outer_contour3d._bounding_box()

    @classmethod
    def from_step(cls, arguments, object_dict):
        contours = []
        contours.append(object_dict[int(arguments[1][0][1:])])

        if object_dict[int(arguments[2])].__class__ is Plane3D:
            return PlaneFace3D.from_contours3d(contours,
                                               name=arguments[0][1:-1])

        elif object_dict[int(arguments[2])].__class__ is CylindricalSurface3D:
            return CylindricalFace3D.from_contour3d(contours, object_dict[
                int(arguments[2])], name=arguments[0][1:-1])

        elif object_dict[int(arguments[2])].__class__ is volmdlr.primitives3D.BSplineExtrusion:
            return BSplineFace3D(contours, object_dict[int(arguments[2])],
                                 name=arguments[0][1:-1])

        elif object_dict[int(arguments[2])].__class__ is volmdlr.faces.BSplineSurface3D:
            # print(object_dict[int(arguments[2])])
            return BSplineFace3D(contours, object_dict[int(arguments[2])],
                                 name=arguments[0][1:-1])

        elif object_dict[int(arguments[2])].__class__ is volmdlr.faces.ToroidalSurface3D:
            return ToroidalFace3D.face_from_contours3d(contours, object_dict[
                int(arguments[2])], name=arguments[0][1:-1])

        elif object_dict[int(arguments[2])].__class__ is volmdlr.faces.ConicalSurface3D:
            return ConicalFace3D.face_from_contours3d(contours,
                                                object_dict[int(arguments[2])],
                                                name=arguments[0][1:-1])

        elif object_dict[int(arguments[2])].__class__ is SphericalSurface3D:
            return SphericalFace3D.from_contour3d(contours, object_dict[
                int(arguments[2])], name=arguments[0][1:-1])

        else:
            print('arguments', arguments)
            raise NotImplementedError(object_dict[int(arguments[2])])

    def delete_double(self, Le):
        Ls = []
        for i in Le:
            if i not in Ls:
                Ls.append(i)
        return Ls

    def min_max(self, Le, pos):
        Ls = []
        for i in range(0, len(Le)):
            Ls.append(Le[i][pos])
        return (min(Ls), max(Ls))

    def range_trigo(list_point):
        points_set = delete_double_point(list_point)
        xmax, xmin = max(pt[0] for pt in points_set), min(
            pt[0] for pt in points_set)
        ymax, ymin = max(pt[1] for pt in points_set), min(
            pt[1] for pt in points_set)
        center = volmdlr.Point2D(((xmax + xmin) / 2, (ymax + ymin) / 2))
        frame2d = Frame2D(center, X2D, Y2D)
        points_test = [frame2d.new_coordinates(pt) for pt in points_set]

        points_2dint = []
        s = 0
        for k in range(0, len(points_test)):
            closest = points_test[s]
            while closest is None:
                s += 1
                closest = points_test[s]
            angle_min = math.atan2(closest.vector[1],
                                   closest.vector[0]) + math.pi
            pos = s
            for i in range(s + 1, len(points_test)):
                close_test = points_test[i]
                if close_test is None:
                    continue
                else:
                    angle_test = math.atan2(close_test.vector[1],
                                            close_test.vector[0]) + math.pi
                    if angle_test < angle_min:  # and dist_test <= dist_min:
                        angle_min = angle_test
                        closest = close_test
                        pos = i
            points_2dint.append(closest)
            points_test[pos] = None

        points_old = [frame2d.old_coordinates(pt) for pt in points_2dint]
        return points_old

    def range_closest(list_point, r1=None, r2=None):
        # use r1, r2 to compare h and r1*angle or r1*angle and r2*angle
        points_set = delete_double_point(list_point)
        if r1 is not None:
            for k in range(0, len(points_set)):
                points_set[k].vector[0] = points_set[k].vector[0] * r1
        if r2 is not None:
            for k in range(0, len(points_set)):
                points_set[k].vector[1] = points_set[k].vector[1] * r2

        points_2dint = [points_set[0]]
        s = 1
        for k in range(1, len(points_set)):
            closest = points_set[s]
            while closest is None:
                s += 1
                closest = points_set[s]
            dist_min = (points_2dint[-1] - closest).Norm()
            pos = s
            for i in range(s + 1, len(points_set)):
                close_test = points_set[i]
                if close_test is None:
                    continue
                else:
                    dist_test = (points_2dint[-1] - close_test).Norm()
                    if dist_test <= dist_min:
                        dist_min = dist_test
                        closest = close_test
                        pos = i
            points_2dint.append(closest)
            points_set[pos] = None

        if r1 is not None:
            for k in range(0, len(points_2dint)):
                points_2dint[k].vector[0] = points_2dint[k].vector[0] / r1
        if r2 is not None:
            for k in range(0, len(points_2dint)):
                points_2dint[k].vector[1] = points_2dint[k].vector[1] / r2

        return points_2dint

    def create_primitives(points):
        primitives = []
        for k in range(0, len(points)):
            if k == len(points) - 1:
                primitives.append(volmdlr.LineSegment2D(points[k], points[0]))
            else:
                primitives.append(volmdlr.LineSegment2D(points[k], points[k + 1]))
        return primitives

    def LS2D_inprimitives(ls_toadd, primitives):
        same = False
        for list_prim in primitives:
            for prim in list_prim:
                if ls_toadd.points[0] == prim.points[0] and ls_toadd.points[
                    -1] == prim.points[-1]:
                    same = True
                elif ls_toadd.points[0] == prim.points[-1] and ls_toadd.points[
                    -1] == prim.points[0]:
                    same = True
                else:
                    continue
        return same

    def triangulation(self):
        mesh2d = self.surface2d.triangulation(min_x_density=self.min_x_density,
                                              min_y_density=self.min_y_density)

        return volmdlr.display.DisplayMesh3D(
            [self.surface3d.point2d_to_3d(p) for p in mesh2d.points],
            mesh2d.triangles)

    def plot2d(self, ax=None):
        if ax is None:
            _, ax = plt.subplots()

        self.outer_contour.MPLPlot()


    def rotation(self, center, axis, angle, copy=True):
        if copy:
            new_surface = self.surface.rotation(center, axis,
                                                angle, copy=True)
            return self.__class__(new_surface, self.outer_contour2d,
                                  self.inner_contours2d)
        else:
            self.surface.rotation(center, axis,
                                  angle, copy=False)



    def translation(self, offset, copy=True):
        if copy:
            new_surface3d = self.surface3d.translation(offset=offset, copy=True)
            return self.__class__(new_surface3d, self.surface2d)
        else:
            self.surface.translation(offset=offset, copy=False)


    def frame_mapping(self, frame, side, copy=True):
        """
        side = 'old' or 'new'
        """
        if copy:
            new_surface = self.surface3d.frame_mapping(frame, side, copy=True)
            return self.__class__(new_surface, self.outer_contour,
                                  self.inner_contours)
        else:
            self.surface3d.frame_mapping(frame, side, copy=False)

    def copy(self):
        new_contours = [contour.copy() for contour in self.contours]
        new_plane = self.plane.copy()
        new_points = [p.copy() for p in self.points]
        return PlaneFace3D(new_contours, new_plane, new_points,
                           self.polygon2D.copy(), self.name)

class PlaneFace3D(Face3D):
    """
    :param contours: The face's contour2D
    :type contours: volmdlr.Contour2D
    :param plane: Plane used to place your face
    :type plane: Plane3D
    """
    _standalone_in_db = True
    _generic_eq = True
    _non_serializable_attributes = ['bounding_box', 'polygon2D']
    _non_eq_attributes = ['name', 'bounding_box']
    _non_hash_attributes = []

    def __init__(self, plane3d, surface2d, name=''):
        # if not isinstance(outer_contour2d, volmdlr.Contour2D):
        #     raise ValueError('Not a contour2D: {}'.format(outer_contour2d))
        Face3D.__init__(self,
                        surface3d=plane3d,
                        surface2d=surface2d,
                        name=name)

    @classmethod
    def _repair_points_and_polygon2d(cls, points, plane):
        if points[0] == points[-1]:
            points = points[:-1]
        polygon_points = [
            p.to_2d(plane.origin, plane.vectors[0], plane.vectors[1]) for p in
            points]
        repaired_points = [p.copy() for p in points]
        polygon2D = volmdlr.Polygon2D(polygon_points)
        if polygon2D.SelfIntersect()[0]:
            repaired_points = [repaired_points[1]] + [
                repaired_points[0]] + repaired_points[2:]
            polygon_points = [polygon_points[1]] + [
                polygon_points[0]] + polygon_points[2:]
            if polygon_points[0] == polygon_points[-1]:
                repaired_points = repaired_points[:-1]
                polygon_points = polygon_points[:-1]
            polygon2D = volmdlr.Polygon2D(polygon_points)
        return repaired_points, polygon2D

    @classmethod
    def from_contours3d(cls,
                        outer_contour3d: volmdlr.wires.Contour3D,
                        inner_contours3d: List[volmdlr.wires.Contour3D]=None,
                        name: str = ''):
        """
        :param outer_contour3d: The face's contour3D
        :param inner_contours3d: A list of the face's inner contours3D
        """
        if outer_contour3d.__class__ == volmdlr.wires.Circle3D:
            u = outer_contour3d.normal.deterministic_unit_normal_vector()
            v = outer_contour3d.normal.cross(u)
            plane3d = Plane3D(frame=volmdlr.Frame3D(outer_contour3d.center,
                                            u, v,
                                            outer_contour3d.normal))
        else:
            ocl = outer_contour3d.length()

            points = [outer_contour3d.point_at_abscissa(i*ocl/3.) for i in range(3)]
            plane3d = Plane3D.from_3_points(*points)

        outer_contour2d = plane3d.contour3d_to_2d(outer_contour3d)

        inner_contours2d = []
        if inner_contours3d is not None:
            for contour in inner_contours3d:
                inner_contours2d.append(contour.to_2d(plane3d.frame.origin,
                                                      plane3d.frame.u,
                                                      plane3d.frame.v,
                                                      ))

        return cls(plane3d=plane3d,
                   surface2d=Surface2D(outer_contour=outer_contour2d,
                                       inner_contours=inner_contours2d),
                   name=name)


    def average_center_point(self):
        """
        excluding holes
        """
        points = self.points
        nb = len(points)
        x = npy.sum([p[0] for p in points]) / nb
        y = npy.sum([p[1] for p in points]) / nb
        z = npy.sum([p[2] for p in points]) / nb
        return volmdlr.Point3D((x, y, z))

    def distance_to_point(self, point, return_other_point=False):
        ## """
        ## Only works if the surface is planar
        ## TODO : this function does not take into account if Face has holes
        ## """
        # On projette le point sur la surface plane
        # Si le point est à l'intérieur de la face, on retourne la distance de projection
        # Si le point est à l'extérieur, on projette le point sur le plan
        # On calcule en 2D la distance entre la projection et le polygone contour
        # On utilise le theroeme de Pytagore pour calculer la distance minimale entre le point et le contour

        projected_pt = point.PlaneProjection3D(self.plane.origin,
                                               self.plane.vectors[0],
                                               self.plane.vectors[1])
        projection_distance = point.point_distance(projected_pt)

        if self.point_on_face(projected_pt):
            if return_other_point:
                return projection_distance, projected_pt
            return projection_distance

        point_2D = point.to_2d(self.plane.origin, self.plane.vectors[0],
                              self.plane.vectors[1])

        border_distance, other_point = self.polygon2D.PointBorderDistance(
            point_2D, return_other_point=True)

        other_point = other_point.to_3d(self.plane.origin,
                                       self.plane.vectors[0],
                                       self.plane.vectors[1])

        if return_other_point:
            return (
                               projection_distance ** 2 + border_distance ** 2) ** 0.5, other_point
        return (projection_distance ** 2 + border_distance ** 2) ** 0.5

    def distance_to_face(self, face2, return_points=False):
        ## """
        ## Only works if the surface is planar
        ## TODO : this function does not take into account if Face has holes
        ## TODO : TRAITER LE CAS OU LA DISTANCE LA PLUS COURTE N'EST PAS D'UN SOMMET
        ## """
        # On calcule la distance entre la face 1 et chaque point de la face 2
        # On calcule la distance entre la face 2 et chaque point de la face 1

        if self.face_intersection(face2) is not None:
            return 0, None, None

        polygon1_points_3D = [volmdlr.Point3D(p.vector) for p in
                              self.contours3d[0].tessel_points]
        polygon2_points_3D = [volmdlr.Point3D(p.vector) for p in
                              face2.contours3d[0].tessel_points]

        distances = []
        if not return_points:
            d_min = face2.distance_to_point(polygon1_points_3D[0])
            for point1 in polygon1_points_3D[1:]:
                d = face2.distance_to_point(point1)
                if d < d_min:
                    d_min = d
            for point2 in polygon2_points_3D:
                d = self.distance_to_point(point2)
                if d < d_min:
                    d_min = d
            return d_min

        else:
            for point1 in polygon1_points_3D:
                d, other_point = face2.distance_to_point(point1,
                                                         return_other_point=True)
                distances.append((d, point1, other_point))
            for point2 in polygon2_points_3D:
                d, other_point = self.distance_to_point(point2,
                                                        return_other_point=True)
                distances.append((d, point2, other_point))

        d_min, point_min, other_point_min = distances[0]
        for distance in distances[1:]:
            if distance[0] < d_min:
                d_min = distance[0]
                point_min = distance[1]
                other_point_min = distance[2]

        return d_min, point_min, other_point_min

    def point_on_face(self, point):
        """
        Tells you if a point is on the 3D face and inside its contour
        """
        ## Only works if the surface is planar
        ## TODO : this function does not take into account if Face has holes

        point_on_plane = self.plane.point_on_plane(point)
        # The point is not in the same plane
        if not point_on_plane:
            print('point not on plane so not on face')
            return False

        point_2D = point.to_2d(self.plane.origin, self.plane.vectors[0],
                              self.plane.vectors[1])

        ### PLOT ###
        #        ax = self.polygon2D.MPLPlot()
        #        point_2D.MPLPlot(ax)
        ############

        if not self.polygon2D.PointBelongs(point_2D):
            ### PLOT ###
            #            ax = self.polygon2D.MPLPlot()
            #            point_2D.MPLPlot(ax)
            #            ax.set_title('DEHORS')
            #            ax.set_aspect('equal')
            ############
            return False
        ### PLOT ###
        #        ax = self.polygon2D.MPLPlot()
        #        point_2D.MPLPlot(ax)
        #        ax.set_title('DEDANS')
        #        ax.set_aspect('equal')
        ############
        return True

    def edge_intersection(self, edge):
        linesegment = volmdlr.LineSegment3D(*edge.points)
        intersection_point = self.plane.linesegment_intersection(linesegment)

        if intersection_point is None:
            return None

        point_on_face_boo = self.point_on_face(intersection_point)
        if not point_on_face_boo:
            return None

        return intersection_point

    def linesegment_intersection(self, linesegment, abscissea=False):
        if abscissea:
            intersection_point, intersection_abscissea = self.plane.linesegment_intersection(
                linesegment, True)
        else:
            intersection_point = self.plane.linesegment_intersection(
                linesegment)

        if intersection_point is None:
            if abscissea:
                return None, None
            return None

        point_on_face_boo = self.point_on_face(intersection_point)

        if not point_on_face_boo:
            if abscissea:
                return None, None
            return None

        if abscissea:
            return intersection_point, intersection_abscissea
        return intersection_point

    def face_intersection(self, face2):
        ## """
        ## Only works if the surface is planar
        ## TODO : this function does not take into account if Face has holes
        ## """
        bbox1 = self.bounding_box
        bbox2 = face2.bounding_box
        if not bbox1.bbox_intersection(bbox2):
            return None

        intersection_points = []

        for edge2 in face2.contours3d[0].edges:
            intersection_point = self.edge_intersection(edge2)
            if intersection_point is not None:
                intersection_points.append(intersection_point)

        for edge1 in self.contours3d[0].edges:
            intersection_point = face2.edge_intersection(edge1)
            if intersection_point is not None:
                intersection_points.append(intersection_point)

        if not intersection_points:
            return None

        return intersection_points

    def plot(self, ax=None):
        fig = plt.figure()
        if ax is None:
            ax = fig.add_subplot(111, projection='3d')

        x = [p[0] for p in self.contours[0].tessel_points]
        y = [p[1] for p in self.contours[0].tessel_points]
        z = [p[2] for p in self.contours[0].tessel_points]

        ax.scatter(x, y, z)
        ax.set_xlabel('X Label')
        ax.set_ylabel('Y Label')
        ax.set_zlabel('Z Label')
        for edge in self.contours[0].edges:
            for point1, point2 in (
            edge.points, edge.points[1:] + [edge.points[0]]):
                xs = [point1[0], point2[0]]
                ys = [point1[1], point2[1]]
                zs = [point1[2], point2[2]]
                line = mpl_toolkits.mplot3d.art3d.Line3D(xs, ys, zs)
                ax.add_line(line)

        plt.show()
        return ax

    def minimum_distance(self, other_face, return_points=False):
        if other_face.__class__ is CylindricalFace3D:
            p1, p2 = other_face.minimum_distance_points_cyl(self)
            if return_points:
                return p1.point_distance(p2), p1, p2
            else:
                return p1.point_distance(p2)

        if other_face.__class__ is PlaneFace3D:
            dmin, p1, p2 = self.distance_to_face(other_face,
                                                 return_points=True)
            if return_points:
                return p1.point_distance(p2), p1, p2
            else:
                return p1.point_distance(p2)

        if other_face.__class__ is ToroidalFace3D:
            p1, p2 = other_face.minimum_distance_points_plane(self)
            if return_points:
                return p1.point_distance(p2), p1, p2
            else:
                return p1.point_distance(p2)

        else:
            return NotImplementedError


class CylindricalFace3D(Face3D):
    """
    :param contours2d: The cylinder's contour2D
    :type contours2d: volmdlr.Contour2D
    :param cylindricalsurface3d: Information about the Cylinder
    :type cylindricalsurface3d: CylindricalSurface3D
    :param points: contours2d's point
    :type points: List of volmdlr.Point2D

    :Example:
        >>> contours2d is rectangular and will create a classic cylinder with x= 2*pi*radius, y=h
    """
    min_x_density = 5
    min_y_density = 1

    def __init__(self,
                 cylindricalsurface3d: CylindricalSurface3D,
                 surface2d: Surface2D,
                 name: str = ''):

        self.radius = cylindricalsurface3d.radius
        self.center = cylindricalsurface3d.frame.origin
        self.normal = cylindricalsurface3d.frame.w
        Face3D.__init__(self, surface3d=cylindricalsurface3d,
                        surface2d=surface2d,
                        name=name)

    @classmethod
    def from_contour3d(cls, contours3d, cylindricalsurface3d, name=''):
        """
        :param contours3d: The cylinder's contour3D
        :type contours3d: Contour3D
        :param cylindricalsurface3d: Information about the Cylinder
        :type cylindricalsurface3d: CylindricalSurface3D

        example
            >>> contours3d is [Arc3D, volmdlr.LineSegment3D, Arc3D]
        """

        frame = cylindricalsurface3d.frame
        radius = cylindricalsurface3d.radius
        size = len(contours3d[0].edges)

        if contours3d[0].edges[0].__class__ is volmdlr.LineSegment3D and \
                contours3d[0].edges[1].__class__ is Arc3D:
            return CylindricalFace3D.from_arc3d(contours3d[0].edges[0],
                                                contours3d[0].edges[1],
                                                cylindricalsurface3d)

        if contours3d[0].edges[0].__class__ is Arc3D and contours3d[0].edges[
            2].__class__ is Arc3D and size <= 4:

            arc1, arc2 = contours3d[0].edges[0], contours3d[0].edges[2]
            c1, c2 = frame.new_coordinates(arc1.center), frame.new_coordinates(
                arc2.center)
            hmin, hmax = min(c1.vector[2], c2.vector[2]), max(c1.vector[2],
                                                              c2.vector[2])
            n1 = arc1.normal
            if n1 == -frame.w:
                arc1.setup_arc(arc1.start, arc1.interior, arc1.end,
                               -arc1.normal)
            start1, end1 = arc1.start, arc1.end
            theta1_1, theta1_2 = posangle_arc(start1, end1, radius, frame)
            if not (
            math.isclose(arc1.angle, abs(theta1_1 - theta1_2), abs_tol=1e-4)):
                if math.isclose(theta1_1, 0, abs_tol=1e-4):
                    theta1_1 = volmdlr.TWO_PI
                elif math.isclose(theta1_2, 0, abs_tol=1e-4):
                    theta1_2 = volmdlr.TWO_PI
                else:
                    # if theta1_2 > theta1_1 :
                    #     theta1_2 -= math.pi
                    # else :
                    #     theta1_1 -= math.pi
                    print('arc1.angle', arc1.angle)
                    print('theta1_1, theta1_2', theta1_1, theta1_2)
                    raise NotImplementedError

            offset1, angle1 = offset_angle(arc1.is_trigo, theta1_1, theta1_2)
            pt1, pt2, pt3, pt4 = volmdlr.Point2D((offset1, hmin)), volmdlr.Point2D(
                (offset1, hmax)), volmdlr.Point2D((offset1 + angle1, hmax)), volmdlr.Point2D(
                (offset1 + angle1, hmin))
            seg1, seg2, seg3, seg4 = volmdlr.LineSegment2D(pt1, pt2), volmdlr.LineSegment2D(
                pt2, pt3), volmdlr.LineSegment2D(pt3, pt4), volmdlr.LineSegment2D(pt4, pt1)
            primitives = [seg1, seg2, seg3, seg4]
            contours2d = [volmdlr.Contour2D(primitives)]
            points = contours2d[0].tessel_points

        else:
            contours2d = CylindricalFace3D.contours3d_to2d(contours3d,
                                                           cylindricalsurface3d)
            points = contours2d[0].tessel_points

        return cls(contours2d, cylindricalsurface3d, points, name=name)

    @classmethod
    def from_arc3d(cls, lineseg, arc,
                   cylindricalsurface3d):  # Work with 2D too
        """
        :param lineseg: The segment which represent the extrusion of the arc
        :type lineseg: volmdlr.LineSegment3D/2D
        :param arc: The Arc circle to extrude
        :type arc: Arc3D/2D, volmdlr.Circle3D/2D
        :param cylindricalsurface3d: Information about the Cylinder
        :type cylindricalsurface3d: CylindricalSurface3D

        Particularity : the frame is the base of the cylinder, it begins there and go in the normal direction
        """
        radius = cylindricalsurface3d.radius
        frame = cylindricalsurface3d.frame
        normal, center = frame.w, frame.origin
        offset = 0
        if arc.__class__.__name__ == 'volmdlr.Circle3D'\
            or arc.__class__.__name__ == 'Circle2D':

            frame_adapt = cylindricalsurface3d.frame
            theta = arc.angle

        else:
            point12d = arc.start
            if point12d.__class__ is volmdlr.Point3D:
                point12d = point12d.to_2d(center, frame.u,
                                         frame.v)
                # Using it to put arc.start at the same height
            point13d = point12d.to_3d(center, frame.u, frame.v)
            if arc.start.__class__ is volmdlr.Point2D:
                u_g2d = Vector2D((arc.start - arc.center).vector)
                u = u_g2d.to_3d(center, frame.u, frame.v)
                u.normalize()
            else:
                u = Vector3D((point13d - center).vector)
                u.normalize()
            v = normal.cross(u)
            v.normalize()

            point_last = arc.end
            if point_last.__class__ is volmdlr.Point3D:
                point_last = point_last.to_2d(center, u, v)

            x, y = point_last.vector[0], point_last.vector[1]

            theta = math.atan2(y, x)
            if theta < 0 or math.isclose(theta, 0, abs_tol=1e-9):
                if arc.angle > math.pi:
                    theta += volmdlr.TWO_PI
                else:
                    offset = theta
                    theta = -theta

            frame_adapt = volmdlr.Frame3D(center, u, v, normal)

        cylindersurface3d = CylindricalSurface3D(frame_adapt, radius)
        segbh = volmdlr.LineSegment2D(volmdlr.Point2D((offset, 0)),
                              volmdlr.Point2D((offset, lineseg.Length())))
        circlestart = volmdlr.LineSegment2D(segbh.points[1],
                                    segbh.points[1] + volmdlr.Point2D((theta, 0)))
        seghb = volmdlr.LineSegment2D(circlestart.points[1],
                              circlestart.points[1] - segbh.points[1] +
                              segbh.points[0])
        circlend = volmdlr.LineSegment2D(seghb.points[1], segbh.points[0])

        edges = [segbh, circlestart, seghb, circlend]
        return cls(cylindersurface3d, volmdlr.Contour2D(edges), [], name='')

    def contours3d_to2d(contours3d, cylindricalsurface3d):
        frame = cylindricalsurface3d.frame
        n = frame.w
        radius = cylindricalsurface3d.radius

        primitives, start_end, all_points = [], [], []
        for edge in contours3d[0].edges:
            new_points = [frame.new_coordinates(pt) for pt in edge.points]
            if edge.__class__ is Arc3D:
                if edge.normal == n or edge.normal == -n:
                    start2d, end2d = CylindricalFace3D.points3d_to2d(
                        new_points, radius)
                    angle2d = abs(end2d[0] - start2d[0])
                    if math.isclose(edge.angle, volmdlr.TWO_PI, abs_tol=1e-6):
                        if start2d == end2d:
                            if math.isclose(start2d.vector[0], volmdlr.TWO_PI,
                                            abs_tol=1e-6):
                                end2d = end2d - volmdlr.Point2D((volmdlr.TWO_PI, 0))
                            else:
                                end2d = end2d + volmdlr.Point2D((volmdlr.TWO_PI, 0))
                    elif not (math.isclose(edge.angle, angle2d, abs_tol=1e-2)):
                        # if math.isclose(angle2d, volmdlr.TWO_PI, abs_tol=1e-2) :
                        if start2d[0] < end2d[0]:
                            end2d = start2d + volmdlr.Point2D((edge.angle, 0))
                        else:
                            end2d = start2d - volmdlr.Point2D((edge.angle, 0))
                    ls_toadd = volmdlr.LineSegment2D(start2d, end2d)
                    same = Face3D.LS2D_inprimitives(ls_toadd, primitives)
                    if same is False:
                        primitives.append([ls_toadd])
                        all_points.extend(ls_toadd.points)
                        start_end.append(ls_toadd.points)

                else:
                    points2d = CylindricalFace3D.points3d_to2d(new_points,
                                                               radius)
                    lines = []
                    for k in range(0, len(points2d) - 1):
                        lines.append(
                            volmdlr.LineSegment2D(points2d[k], points2d[k + 1]))
                    points, prim_list = [], []
                    for ls_toadd in lines:
                        same = Face3D.LS2D_inprimitives(ls_toadd, primitives)
                        if same is False:
                            prim_list.append(ls_toadd)
                            points.extend(ls_toadd.points)
                    if len(points) > 0:
                        all_points.extend(points)
                        primitives.append(prim_list)
                        start_end.append([points[0], points[-1]])

            elif edge.__class__ is volmdlr.LineSegment3D:
                start2d, end2d = CylindricalFace3D.points3d_to2d(new_points,
                                                                 radius)
                ls_toadd = volmdlr.LineSegment2D(start2d, end2d)
                same = Face3D.LS2D_inprimitives(ls_toadd, primitives)
                if same is False:
                    primitives.append([ls_toadd])
                    all_points.extend(ls_toadd.points)
                    start_end.append(ls_toadd.points)

            else:
                points2d = CylindricalFace3D.points3d_to2d(new_points, radius)
                lines = []
                for k in range(0, len(points2d) - 1):
                    lines.append(volmdlr.LineSegment2D(points2d[k], points2d[k + 1]))
                points, prim_list = [], []
                for ls_toadd in lines:
                    same = Face3D.LS2D_inprimitives(ls_toadd, primitives)
                    if same is False:
                        prim_list.append(ls_toadd)
                        points.extend(ls_toadd.points)
                if len(points) > 0:
                    all_points.extend(points)
                    primitives.append(prim_list)
                    start_end.append([points[0], points[-1]])

        points_se, primitives_se = [], []
        for double in start_end:
            primitives_se.append(volmdlr.LineSegment2D(double[0], double[1]))
            points_se.extend(double)
        poly_se = volmdlr.Polygon2D(points_se)

        xmax, xmin = max(pt[0] for pt in points_se), min(
            pt[0] for pt in points_se)
        ymax, ymin = max(pt[1] for pt in points_se), min(
            pt[1] for pt in points_se)
        pt1, pt2, pt3, pt4 = volmdlr.Point2D((xmin, ymin)), volmdlr.Point2D(
            (xmin, ymax)), volmdlr.Point2D((xmax, ymin)), volmdlr.Point2D((xmax, ymax))
        diag1, diag2 = volmdlr.LineSegment2D(pt1, pt4), volmdlr.LineSegment2D(pt2, pt3)
        diag1_cut, diag2_cut = [], []
        diag1_pointcut, diag2_pointcut = [], []
        for enum, l in enumerate(primitives_se):
            cut1 = diag1.line_intersections(l)
            cut2 = diag2.line_intersections(l)
            if cut1 is not None:
                diag1_cut.append(enum)
                diag1_pointcut.append(cut1)
            if cut2 is not None:
                diag2_cut.append(enum)
                diag2_pointcut.append(cut2)

        points_common = []
        for enum1, pos1 in enumerate(diag1_cut):
            for enum2, pos2 in enumerate(diag2_cut):
                if pos1 == pos2:
                    points_common.append(primitives_se[pos1].points)

        if len(points_common) >= 1:
            solve = False
            for couple in points_common:
                check1, check2 = poly_se.PointBelongs(
                    couple[0]), poly_se.PointBelongs(couple[1])
                start, end = couple[0].vector[0], couple[1].vector[0]
                if math.isclose(start, end, abs_tol=5e-2):
                    intersect = min(start, end)
                    if math.isclose(intersect, math.pi, abs_tol=5e-2):
                        points_sing = check_singularity(all_points)
                        pt0, pt2pi = 0, 0
                        for pt in points_sing:
                            if math.isclose(pt.vector[0], 0, abs_tol=1e-2):
                                pt0 += 1
                            elif math.isclose(pt.vector[0], volmdlr.TWO_PI,
                                              abs_tol=1e-2):
                                pt2pi += 1
                        points_sing.sort(key=lambda pt: pt[1])
                        points_sing.sort(key=lambda pt: pt[0])
                        if pt2pi != 0 and pt0 == 0:
                            points = [pt.copy() for pt in points_sing[::-1]]
                            points_sing = points
                        points_range = CylindricalFace3D.range_closest(
                            points_sing, radius, frame)
                        all_points = delete_double_point(points_range)
                        break
                    elif math.isclose(intersect, 0,
                                      abs_tol=1e-6) or math.isclose(intersect,
                                                                    volmdlr.TWO_PI,
                                                                    abs_tol=1e-6) or (
                            not check1 or not check2):
                        all_points = check_singularity(all_points)

                        points_cleaned = delete_double_point(all_points)
                        all_points = [pt.copy() for pt in points_cleaned]
                        all_points.sort(key=lambda pt: pt[0])
                        d1, d2 = (all_points[0] - all_points[-1]).Norm(), (
                                    all_points[0] - all_points[-2]).Norm()
                        if d2 < d1:
                            last = all_points[-1].copy()
                            all_points[-1] = all_points[-2].copy()
                            all_points[-2] = last
                        break
                    else:
                        points = []
                        for list_prim in primitives:
                            for k, prim in enumerate(list_prim):
                                new_list_points = []
                                change = 0
                                for pt in prim.points:
                                    if pt[0] < intersect:
                                        change += 1
                                        if math.isclose(pt[0], 0,
                                                        abs_tol=1e-1):
                                            new_list_points.append(volmdlr.Point2D((
                                                                           intersect + volmdlr.TWO_PI,
                                                                           pt[
                                                                               1])))
                                        else:
                                            new_list_points.append(volmdlr.Point2D(
                                                (volmdlr.TWO_PI + pt[0], pt[1])))
                                    elif math.isclose(pt[0], intersect,
                                                      abs_tol=1e-1):
                                        change += 1
                                        new_list_points.append(volmdlr.Point2D(
                                            (volmdlr.TWO_PI + pt[0], pt[1])))
                                    else:
                                        new_list_points.append(pt)
                                if change > 0:
                                    points.extend(new_list_points)
                                    # list_prim[k] = volmdlr.LineSegment2D(new_list_points[0], new_list_points[1])
                                else:
                                    points.extend(prim.points)
                                    continue
                        points_cleaned = delete_double_point(points)
                        all_points = Face3D.range_trigo(points_cleaned)
                    solve = True
                else:
                    points_cleaned = delete_double_point(all_points)
                    all_points = [pt.copy() for pt in points_cleaned]
                    all_points.sort(key=lambda pt: pt[0])
                    d1, d2 = (all_points[0] - all_points[-1]).Norm(), (
                                all_points[0] - all_points[-2]).Norm()
                    if d2 < d1:
                        last = all_points[-1].copy()
                        all_points[-1] = all_points[-2].copy()
                        all_points[-2] = last
        else:
            points_cleaned = delete_double_point(all_points)
            all_points = [pt.copy() for pt in points_cleaned]
            all_points.sort(key=lambda pt: pt[0])
            d1, d2 = (all_points[0] - all_points[-1]).Norm(), (
                        all_points[0] - all_points[-2]).Norm()
            if d2 < d1:
                last = all_points[-1].copy()
                all_points[-1] = all_points[-2].copy()
                all_points[-2] = last

        primitives = Face3D.create_primitives(all_points)

        l_vert = volmdlr.LineSegment2D((pt2 + pt4) / 2, (pt1 + pt3) / 2)
        solve = False
        for prim in primitives:
            if solve:
                break
            intersect = prim.line_intersections(l_vert)
            if intersect is not None:
                x_intersect = intersect.vector[0]
                y_intersect = intersect.vector[1]
                value1, value2 = ymax - 0.2 * (ymax - ymin), ymin + 0.2 * (
                            ymax - ymin)
                if y_intersect < max(value1, value2) and y_intersect > min(
                        value1, value2):
                    points = []
                    for k, prim in enumerate(primitives):
                        new_list_points, change = [], 0
                        for pt in prim.points:
                            if pt[0] < x_intersect:
                                change += 1
                                if math.isclose(pt[0], 0, abs_tol=1e-1):
                                    new_list_points.append(volmdlr.Point2D(
                                        (x_intersect + volmdlr.TWO_PI, pt[1])))
                                else:
                                    new_list_points.append(
                                        volmdlr.Point2D((volmdlr.TWO_PI + pt[0], pt[1])))
                            else:
                                new_list_points.append(pt)
                        if change > 0:
                            points.extend(new_list_points)
                            primitives[k] = volmdlr.LineSegment2D(new_list_points[0],
                                                          new_list_points[1])
                        else:
                            points.extend(prim.points)
                            continue
                    solve = True
                    points_cleaned = delete_double_point(points)
                    all_points = Face3D.range_trigo(points_cleaned)
                    primitives = Face3D.create_primitives(all_points)

            contour2d = [volmdlr.Contour2D(primitives)]
        return contour2d

    def range_closest(list_point, radius, frame):
        points_set = delete_double_point(list_point)
        points_set3D = CylindricalFace3D.points2d_to3d(None, [points_set],
                                                       radius, frame)

        points_3dint = [points_set3D[0]]
        points_2dint = [points_set[0]]
        s = 1
        for k in range(1, len(points_set)):
            closest = points_set3D[s]
            while closest is None:
                s += 1
                closest = points_set3D[s]
            dist_min = (points_3dint[-1] - closest).Norm()
            pos = s
            for i in range(s + 1, len(points_set3D)):
                close_test = points_set3D[i]
                if close_test is None:
                    continue
                else:
                    dist_test = (points_3dint[-1] - close_test).Norm()
                    if dist_test <= dist_min:
                        dist_min = dist_test
                        closest = close_test
                        pos = i
            points_2dint.append(points_set[pos])
            points_set3D[pos] = None

        return points_2dint

    def MPLPlotpoints(self, ax=None, color='k'):
        if ax is None:
            fig = plt.figure()
            ax = fig.add_subplot(111, projection='3d')
        else:
            fig = ax.figure

        x, y, z = [], [], []
        for px, py, pz in self.points:
            x.append(px)
            y.append(py)
            z.append(pz)
        x.append(x[0])
        y.append(y[0])
        z.append(z[0])
        ax.plot(x, y, z, color)
        return ax

    def MPLPlotcontours(self, ax=None, color='k'):
        if ax is None:
            fig = plt.figure()
            ax = fig.add_subplot(111, projection='3d')
        else:
            fig = ax.figure

        x = []
        y = []
        z = []
        for px, py, pz in self.contours[0].tessel_points:
            x.append(px)
            y.append(py)
            z.append(pz)
        x.append(x[0])
        y.append(y[0])
        z.append(z[0])
        ax.plot(x, y, z, color)
        return ax

    # def frame_mapping(self, frame, side, copy=True):
    #     if copy:
    #         new_cylindricalsurface3d = CylindricalSurface3D.frame_mapping(
    #             frame, side, copy)
    #         return CylindricalFace3D(self.contours2d, new_cylindricalsurface3d,
    #                                  points=self.points, name=self.name)
    #     else:
    #         self.cylindricalsurface3d.frame_mapping(frame, side, copy=False)

    def minimum_maximum(self, contour2d, radius):
        points = contour2d.tessel_points

        min_h, min_theta = min([pt[1] for pt in points]), min(
            [pt[0] for pt in points])
        max_h, max_theta = max([pt[1] for pt in points]), max(
            [pt[0] for pt in points])
        return min_h, min_theta, max_h, max_theta

    def minimum_distance_points_cyl(self, other_cyl):
        r1, r2 = self.radius, other_cyl.radius
        min_h1, min_theta1, max_h1, max_theta1 = self.minimum_maximum(
            self.contours2d[0], r1)

        n1 = self.normal
        u1 = self.cylindricalsurface3d.frame.u
        v1 = self.cylindricalsurface3d.frame.v
        frame1 = volmdlr.Frame3D(self.center, u1, v1, n1)

        min_h2, min_theta2, max_h2, max_theta2 = self.minimum_maximum(
            other_cyl.contours2d[0], r2)

        n2 = other_cyl.normal
        u2 = other_cyl.cylindricalsurface3d.frame.u
        v2 = other_cyl.cylindricalsurface3d.frame.v
        frame2 = volmdlr.Frame3D(other_cyl.center, u2, v2, n2)
        # st2 = volmdlr.Point3D((r2*math.cos(min_theta2), r2*math.sin(min_theta2), min_h2))
        # start2 = frame2.old_coordinates(st2)

        w = other_cyl.center - self.center

        n1n1, n1u1, n1v1, n1n2, n1u2, n1v2 = n1.dot(n1), n1.dot(u1), n1.dot(
            v1), n1.dot(n2), n1.dot(u2), n1.dot(v2)
        u1u1, u1v1, u1n2, u1u2, u1v2 = u1.dot(u1), u1.dot(v1), u1.dot(
            n2), u1.dot(u2), u1.dot(v2)
        v1v1, v1n2, v1u2, v1v2 = v1.dot(v1), v1.dot(n2), v1.dot(u2), v1.dot(v2)
        n2n2, n2u2, n2v2 = n2.dot(n2), n2.dot(u2), n2.dot(v2)
        u2u2, u2v2, v2v2 = u2.dot(u2), u2.dot(v2), v2.dot(v2)

        w2, wn1, wu1, wv1, wn2, wu2, wv2 = w.dot(w), w.dot(n1), w.dot(
            u1), w.dot(v1), w.dot(n2), w.dot(u2), w.dot(v2)

        # x = (theta1, h1, theta2, h2)
        def distance_squared(x):
            return (n1n1 * (x[1] ** 2) + u1u1 * ((math.cos(x[0])) ** 2) * (
                        r1 ** 2) + v1v1 * ((math.sin(x[0])) ** 2) * (r1 ** 2)
                    + w2 + n2n2 * (x[3] ** 2) + u2u2 * (
                            (math.cos(x[2])) ** 2) * (r2 ** 2) + v2v2 * (
                                (math.sin(x[2])) ** 2) * (r2 ** 2)
                    + 2 * x[1] * r1 * math.cos(x[0]) * n1u1 + 2 * x[
                        1] * r1 * math.sin(x[0]) * n1v1 - 2 * x[1] * wn1
                    - 2 * x[1] * x[3] * n1n2 - 2 * x[1] * r2 * math.cos(
                        x[2]) * n1u2 - 2 * x[1] * r2 * math.sin(x[2]) * n1v2
                    + 2 * math.cos(x[0]) * math.sin(x[0]) * u1v1 * (
                                r1 ** 2) - 2 * r1 * math.cos(x[0]) * wu1
                    - 2 * r1 * x[3] * math.cos(
                        x[0]) * u1n2 - 2 * r1 * r2 * math.cos(x[0]) * math.cos(
                        x[2]) * u1u2
                    - 2 * r1 * r2 * math.cos(x[0]) * math.sin(
                        x[2]) * u1v2 - 2 * r1 * math.sin(x[0]) * wv1
                    - 2 * r1 * x[3] * math.sin(
                        x[0]) * v1n2 - 2 * r1 * r2 * math.sin(x[0]) * math.cos(
                        x[2]) * v1u2
                    - 2 * r1 * r2 * math.sin(x[0]) * math.sin(
                        x[2]) * v1v2 + 2 * x[3] * wn2 + 2 * r2 * math.cos(
                        x[2]) * wu2
                    + 2 * r2 * math.sin(x[2]) * wv2 + 2 * x[3] * r2 * math.cos(
                        x[2]) * n2u2 + 2 * x[3] * r2 * math.sin(x[2]) * n2v2
                    + 2 * math.cos(x[2]) * math.sin(x[2]) * u2v2 * (r2 ** 2))

        x01 = npy.array([(min_theta1 + max_theta1) / 2, (min_h1 + max_h1) / 2,
                         (min_theta2 + max_theta2) / 2, (min_h2 + max_h2) / 2])
        x02 = npy.array([min_theta1, (min_h1 + max_h1) / 2,
                         min_theta2, (min_h2 + max_h2) / 2])
        x03 = npy.array([max_theta1, (min_h1 + max_h1) / 2,
                         max_theta2, (min_h2 + max_h2) / 2])

        minimax = [(min_theta1, min_h1, min_theta2, min_h2),
                   (max_theta1, max_h1, max_theta2, max_h2)]

        res1 = scp.optimize.least_squares(distance_squared, x01,
                                          bounds=minimax)
        res2 = scp.optimize.least_squares(distance_squared, x02,
                                          bounds=minimax)
        res3 = scp.optimize.least_squares(distance_squared, x03,
                                          bounds=minimax)

        pt1 = volmdlr.Point3D(
            (r1 * math.cos(res1.x[0]), r1 * math.sin(res1.x[0]), res1.x[1]))
        p1 = frame1.old_coordinates(pt1)
        pt2 = volmdlr.Point3D(
            (r2 * math.cos(res1.x[2]), r2 * math.sin(res1.x[2]), res1.x[3]))
        p2 = frame2.old_coordinates(pt2)
        d = p1.point_distance(p2)
        result = res1

        res = [res2, res3]
        for couple in res:
            pttest1 = volmdlr.Point3D((r1 * math.cos(couple.x[0]),
                               r1 * math.sin(couple.x[0]), couple.x[1]))
            pttest2 = volmdlr.Point3D((r2 * math.cos(couple.x[2]),
                               r2 * math.sin(couple.x[2]), couple.x[3]))
            ptest1 = frame1.old_coordinates(pttest1)
            ptest2 = frame2.old_coordinates(pttest2)
            dtest = ptest1.point_distance(ptest2)
            if dtest < d:
                result = couple
                p1, p2 = ptest1, ptest2

        pt1_2d, pt2_2d = volmdlr.Point2D((result.x[0], result.x[1])), volmdlr.Point2D(
            (result.x[2], result.x[3]))

        if not (self.contours2d[0].point_belongs(pt1_2d)):
            # Find the closest one
            points_contours1 = self.contours2d[0].tessel_points

            poly1 = volmdlr.Polygon2D(points_contours1)
            d1, new_pt1_2d = poly1.PointBorderDistance(pt1_2d,
                                                       return_other_point=True)
            pt1 = volmdlr.Point3D((r1 * math.cos(new_pt1_2d.vector[0]),
                           r1 * math.sin(new_pt1_2d.vector[0]),
                           new_pt1_2d.vector[1]))
            p1 = frame1.old_coordinates(pt1)

        if not (other_cyl.contours2d[0].point_belongs(pt2_2d)):
            # Find the closest one
            points_contours2 = other_cyl.contours2d[0].tessel_points

            poly2 = volmdlr.Polygon2D(points_contours2)
            d2, new_pt2_2d = poly2.PointBorderDistance(pt2_2d,
                                                       return_other_point=True)
            pt2 = volmdlr.Point3D((r2 * math.cos(new_pt2_2d.vector[0]),
                           r2 * math.sin(new_pt2_2d.vector[0]),
                           new_pt2_2d.vector[1]))
            p2 = frame2.old_coordinates(pt2)

        return p1, p2

    def minimum_distance_points_plane(self,
                                      planeface):  # Planeface with contour2D
        #### ADD THE FACT THAT PLANEFACE.CONTOURS : [0] = contours totale, le reste = trous
        r = self.radius
        min_h1, min_theta1, max_h1, max_theta1 = self.minimum_maximum(
            self.contours2d[0], r)

        n1 = self.normal
        u1 = self.cylindricalsurface3d.frame.u
        v1 = self.cylindricalsurface3d.frame.v
        frame1 = volmdlr.Frame3D(self.center, u1, v1, n1)
        # st1 = volmdlr.Point3D((r*math.cos(min_theta1), r*math.sin(min_theta1), min_h1))
        # start1 = frame1.old_coordinates(st1)

        poly2d = planeface.polygon2D
        pfpoints = poly2d.points
        xmin, ymin = min([pt[0] for pt in pfpoints]), min(
            [pt[1] for pt in pfpoints])
        xmax, ymax = max([pt[0] for pt in pfpoints]), max(
            [pt[1] for pt in pfpoints])
        origin, vx, vy = planeface.plane.origin, planeface.plane.vectors[0], \
                         planeface.plane.vectors[1]
        pf1_2d, pf2_2d = volmdlr.Point2D((xmin, ymin)), volmdlr.Point2D((xmin, ymax))
        pf3_2d, pf4_2d = volmdlr.Point2D((xmax, ymin)), volmdlr.Point2D((xmax, ymax))
        pf1, pf2 = pf1_2d.to_3d(origin, vx, vy), pf2_2d.to_3d(origin, vx, vy)
        pf3, _ = pf3_2d.to_3d(origin, vx, vy), pf4_2d.to_3d(origin, vx, vy)

        u, v = (pf3 - pf1), (pf2 - pf1)
        u.normalize()
        v.normalize()

        w = pf1 - self.center

        n1n1, n1u1, n1v1, n1u, n1v = n1.dot(n1), n1.dot(u1), n1.dot(
            v1), n1.dot(u), n1.dot(v)
        u1u1, u1v1, u1u, u1v = u1.dot(u1), u1.dot(v1), u1.dot(u), u1.dot(v)
        v1v1, v1u, v1v = v1.dot(v1), v1.dot(u), v1.dot(v)
        uu, uv, vv = u.dot(u), u.dot(v), v.dot(v)

        w2, wn1, wu1, wv1, wu, wv = w.dot(w), w.dot(n1), w.dot(u1), w.dot(
            v1), w.dot(u), w.dot(v)

        # x = (h, theta, x, y)
        def distance_squared(x):
            return (n1n1 * (x[0] ** 2) + ((math.cos(x[1])) ** 2) * u1u1 * (
                        r ** 2) + ((math.sin(x[1])) ** 2) * v1v1 * (r ** 2)
                    + w2 + uu * (x[2] ** 2) + vv * (x[3] ** 2) + 2 * x[
                        0] * math.cos(x[1]) * r * n1u1
                    + 2 * x[0] * math.sin(x[1]) * r * n1v1 - 2 * x[
                        0] * wn1 - 2 * x[0] * x[2] * n1u
                    - 2 * x[0] * x[3] * n1v + 2 * math.sin(x[1]) * math.cos(
                        x[1]) * u1v1 * (r ** 2)
                    - 2 * r * math.cos(x[1]) * wu1 - 2 * r * x[2] * math.cos(
                        x[1]) * u1u
                    - 2 * r * x[3] * math.sin(x[1]) * u1v - 2 * r * math.sin(
                        x[1]) * wv1
                    - 2 * r * x[2] * math.sin(x[1]) * v1u - 2 * r * x[
                        3] * math.sin(x[1]) * v1v
                    + 2 * x[2] * wu + 2 * x[3] * wv + 2 * x[2] * x[3] * uv)

        x01 = npy.array([(min_h1 + max_h1) / 2, (min_theta1 + max_theta1) / 2,
                         (xmax - xmin) / 2, (ymax - ymin) / 2])

        minimax = [(min_h1, min_theta1, 0, 0),
                   (max_h1, max_theta1, xmax - xmin, ymax - ymin)]

        res1 = scp.optimize.least_squares(distance_squared, x01,
                                          bounds=minimax)

        pt1 = volmdlr.Point3D(
            (r * math.cos(res1.x[1]), r * math.sin(res1.x[1]), res1.x[0]))
        p1 = frame1.old_coordinates(pt1)
        p2 = pf1 + res1.x[2] * u + res1.x[3] * v
        pt1_2d = volmdlr.Point2D((res1.x[1], res1.x[0]))
        pt2_2d = p2.to_2d(pf1, u, v)

        if not (self.contours2d[0].point_belongs(pt1_2d)):
            # Find the closest one
            points_contours1 = self.contours2d[0].tessel_points

            poly1 = volmdlr.Polygon2D(points_contours1)
            d1, new_pt1_2d = poly1.PointBorderDistance(pt1_2d,
                                                       return_other_point=True)
            pt1 = volmdlr.Point3D((r * math.cos(new_pt1_2d.vector[0]),
                           r * math.sin(new_pt1_2d.vector[0]),
                           new_pt1_2d.vector[1]))
            p1 = frame1.old_coordinates(pt1)

        if not (planeface.contours[0].point_belongs(pt2_2d)):
            # Find the closest one
            d2, new_pt2_2d = planeface.polygon2D.PointBorderDistance(pt2_2d,
                                                                     return_other_point=True)

            p2 = new_pt2_2d.to_3d(pf1, u, v)

        return p1, p2

    def minimum_distance(self, other_face, return_points=False):
        if other_face.__class__ is CylindricalFace3D:
            p1, p2 = self.minimum_distance_points_cyl(other_face)
            if return_points:
                return p1.point_distance(p2), p1, p2
            else:
                return p1.point_distance(p2)

        if other_face.__class__ is PlaneFace3D:
            p1, p2 = self.minimum_distance_points_plane(other_face)
            if return_points:
                return p1.point_distance(p2), p1, p2
            else:
                return p1.point_distance(p2)

        if other_face.__class__ is ToroidalFace3D:
            p1, p2 = other_face.minimum_distance_points_cyl(self)
            if return_points:
                return p1.point_distance(p2), p1, p2
            else:
                return p1.point_distance(p2)

        else:
            return NotImplementedError


class ToroidalFace3D(Face3D):
    """
    :param contours2d: The Tore's contour2D
    :type contours2d: volmdlr.Contour2D
    :param toroidalsurface3d: Information about the Tore
    :type toroidalsurface3d: ToroidalSurface3D
    :param theta: angle of cut in main circle direction
    :param phi: angle of cut in secondary circle direction
    :type points: List of float

    Example
        contours2d is rectangular and will create a classic tore with x:2*pi, y:2*pi
        x is for exterior, and y for the circle to revolute
        points = [pi, 2*pi] for an half tore
    """
    min_x_density = 5
    min_y_density = 1

    def __init__(self, toroidalsurface3d: ToroidalSurface3D,
                 surface2d: Surface2D,
                 name: str = ''):

        # self.toroidalsurface3d = toroidalsurface3d

        self.center = toroidalsurface3d.frame.origin
        self.normal = toroidalsurface3d.frame.w

        theta_min, theta_max, phi_min, phi_max = surface2d.outer_contour.bounding_rectangle()

        self.theta_min = theta_min
        self.theta_max = theta_max
        self.phi_min = phi_min
        self.phi_max = phi_max

        # contours3d = [self.toroidalsurface3d.contour2d_to_3d(c)\
        #               for c in [outer_contour2d]+inners_contours2d]

        Face3D.__init__(self,
                        surface3d=toroidalsurface3d,
                        surface2d=surface2d,
                        name=name)



    def points_resolution(self, line, pos,
                          resolution):  # With a resolution wished
        points = []
        points.append(line.points[0])
        limit = line.points[1].vector[pos]
        start = line.points[0].vector[pos]
        vec = [0, 0]
        vec[pos] = start
        echelon = [line.points[0].vector[0] - vec[0],
                   line.points[0].vector[1] - vec[1]]
        flag = start + resolution
        while flag < limit:
            echelon[pos] = flag
            flag += resolution
            points.append(volmdlr.Point2D(echelon))
        points.append(line.points[1])
        return points

    def _bounding_box(self):
        return self.surface3d._bounding_box()


    def minimum_maximum_tore(self, contour2d):
        points = contour2d.tessel_points

        min_phi, min_theta = min([pt[1] for pt in points]), min(
            [pt[0] for pt in points])
        max_phi, max_theta = max([pt[1] for pt in points]), max(
            [pt[0] for pt in points])
        return min_phi, min_theta, max_phi, max_theta


    def minimum_distance_points_tore(self, other_tore):
        R1, r1, R2, r2 = self.rcenter, self.rcircle, other_tore.rcenter, other_tore.rcircle

        min_phi1, min_theta1, max_phi1, max_theta1 = self.minimum_maximum_tore(
            self.contours2d[0])

        # start1 = self.start
        n1 = self.normal
        u1 = self.toroidalsurface3d.frame.u
        v1 = self.toroidalsurface3d.frame.v
        frame1 = volmdlr.Frame3D(self.center, u1, v1, n1)
        # start1 = self.points2d_to3d([[min_theta1, min_phi1]], R1, r1, frame1)

        min_phi2, min_theta2, max_phi2, max_theta2 = self.minimum_maximum_tore(
            other_tore.contours2d[0])

        # start2 = other_tore.start
        n2 = other_tore.normal
        u2 = other_tore.toroidalsurface3d.frame.u
        v2 = other_tore.toroidalsurface3d.frame.v
        frame2 = volmdlr.Frame3D(other_tore.center, u2, v2, n2)
        # start2 = other_tore.points2d_to3d([[min_theta2, min_phi2]], R2, r2, frame2)

        w = other_tore.center - self.center

        n1n1, n1u1, n1v1, n1n2, n1u2, n1v2 = n1.dot(n1), n1.dot(u1), n1.dot(
            v1), n1.dot(n2), n1.dot(u2), n1.dot(v2)
        u1u1, u1v1, u1n2, u1u2, u1v2 = u1.dot(u1), u1.dot(v1), u1.dot(
            n2), u1.dot(u2), u1.dot(v2)
        v1v1, v1n2, v1u2, v1v2 = v1.dot(v1), v1.dot(n2), v1.dot(u2), v1.dot(v2)
        n2n2, n2u2, n2v2 = n2.dot(n2), n2.dot(u2), n2.dot(v2)
        u2u2, u2v2, v2v2 = u2.dot(u2), u2.dot(v2), v2.dot(v2)

        w2, wn1, wu1, wv1, wn2, wu2, wv2 = w.dot(w), w.dot(n1), w.dot(
            u1), w.dot(v1), w.dot(n2), w.dot(u2), w.dot(v2)

        # x = (phi1, theta1, phi2, theta2)
        def distance_squared(x):
            return (u1u1 * (((R1 + r1 * math.cos(x[0])) * math.cos(x[1])) ** 2)
                    + v1v1 * (((R1 + r1 * math.cos(x[0])) * math.sin(
                        x[1])) ** 2)
                    + n1n1 * ((math.sin(x[0])) ** 2) * (r1 ** 2) + w2
                    + u2u2 * (((R2 + r2 * math.cos(x[2])) * math.cos(
                        x[3])) ** 2)
                    + v2v2 * (((R2 + r2 * math.cos(x[2])) * math.sin(
                        x[3])) ** 2)
                    + n2n2 * ((math.sin(x[2])) ** 2) * (r2 ** 2)
                    + 2 * u1v1 * math.cos(x[1]) * math.sin(x[1]) * (
                                (R1 + r1 * math.cos(x[0])) ** 2)
                    + 2 * (R1 + r1 * math.cos(x[0])) * math.cos(
                        x[1]) * r1 * math.sin(x[0]) * n1u1
                    - 2 * (R1 + r1 * math.cos(x[0])) * math.cos(x[1]) * wu1
                    - 2 * (R1 + r1 * math.cos(x[0])) * (
                                R2 + r2 * math.cos(x[2])) * math.cos(
                        x[1]) * math.cos(x[3]) * u1u2
                    - 2 * (R1 + r1 * math.cos(x[0])) * (
                                R2 + r2 * math.cos(x[2])) * math.cos(
                        x[1]) * math.sin(x[3]) * u1v2
                    - 2 * (R1 + r1 * math.cos(x[0])) * math.cos(
                        x[1]) * r2 * math.sin(x[2]) * u1n2
                    + 2 * (R1 + r1 * math.cos(x[0])) * math.sin(
                        x[1]) * r1 * math.sin(x[0]) * n1v1
                    - 2 * (R1 + r1 * math.cos(x[0])) * math.sin(x[1]) * wv1
                    - 2 * (R1 + r1 * math.cos(x[0])) * (
                                R2 + r2 * math.cos(x[2])) * math.sin(
                        x[1]) * math.cos(x[3]) * v1u2
                    - 2 * (R1 + r1 * math.cos(x[0])) * (
                                R2 + r2 * math.cos(x[2])) * math.sin(
                        x[1]) * math.sin(x[3]) * v1v2
                    - 2 * (R1 + r1 * math.cos(x[0])) * math.sin(
                        x[1]) * r2 * math.sin(x[2]) * v1n2
                    - 2 * r1 * math.sin(x[0]) * wn1
                    - 2 * r1 * math.sin(x[0]) * (
                                R2 + r2 * math.cos(x[2])) * math.cos(
                        x[3]) * n1u2
                    - 2 * r1 * math.sin(x[0]) * (
                                R2 + r2 * math.cos(x[2])) * math.sin(
                        x[3]) * n1v2
                    - 2 * r1 * r2 * math.sin(x[0]) * math.sin(x[2]) * n1n2
                    + 2 * (R2 + r2 * math.cos(x[2])) * math.cos(x[3]) * wu2
                    + 2 * (R2 + r2 * math.cos(x[2])) * math.sin(x[3]) * wv2
                    + 2 * r2 * math.sin(x[2]) * wn2
                    + 2 * u2v2 * math.cos(x[3]) * math.sin(x[3]) * (
                                (R2 + r2 * math.cos(x[2])) ** 2)
                    + 2 * math.cos(x[3]) * (
                                R2 + r2 * math.cos(x[2])) * r2 * math.sin(
                        x[2]) * n2u2
                    + 2 * math.sin(x[3]) * (
                                R2 + r2 * math.cos(x[2])) * r2 * math.sin(
                        x[2]) * n2v2)

        x01 = npy.array(
            [(min_phi1 + max_phi1) / 2, (min_theta1 + max_theta1) / 2,
             (min_phi2 + max_phi2) / 2, (min_theta2 + max_theta2) / 2])
        x02 = npy.array([min_phi1, min_theta1,
                         min_phi2, min_theta2])
        x03 = npy.array([max_phi1, max_theta1,
                         max_phi2, max_theta2])

        minimax = [(min_phi1, min_theta1, min_phi2, min_theta2),
                   (max_phi1, max_theta1, max_phi2, max_theta2)]

        res1 = scp.optimize.least_squares(distance_squared, x01,
                                          bounds=minimax)
        res2 = scp.optimize.least_squares(distance_squared, x02,
                                          bounds=minimax)
        res3 = scp.optimize.least_squares(distance_squared, x03,
                                          bounds=minimax)

        # frame1, frame2 = volmdlr.Frame3D(self.center, u1, v1, n1), volmdlr.Frame3D(other_tore.center, u2, v2, n2)
        pt1 = self.points2d_to3d([[res1.x[1], res1.x[0]]], R1, r1, frame1)
        pt2 = self.points2d_to3d([[res1.x[3], res1.x[2]]], R2, r2, frame2)
        p1, p2 = pt1[0], pt2[0]
        d = p1.point_distance(p2)
        result = res1

        res = [res2, res3]
        for couple in res:
            ptest1 = self.points2d_to3d([[couple.x[1], couple.x[0]]], R1, r1,
                                        frame1)
            ptest2 = self.points2d_to3d([[couple.x[3], couple.x[2]]], R2, r2,
                                        frame2)
            dtest = ptest1[0].point_distance(ptest2[0])
            if dtest < d:
                result = couple
                p1, p2 = ptest1[0], ptest2[0]

        pt1_2d, pt2_2d = volmdlr.Point2D((result.x[1], result.x[0])), volmdlr.Point2D(
            (result.x[3], result.x[2]))

        if not (self.contours2d[0].point_belongs(pt1_2d)):
            # Find the closest one
            points_contours1 = self.contours2d[0].tessel_points

            poly1 = volmdlr.Polygon2D(points_contours1)
            d1, new_pt1_2d = poly1.PointBorderDistance(pt1_2d,
                                                       return_other_point=True)

            pt1 = self.points2d_to3d([new_pt1_2d], R1, r1, frame1)
            p1 = pt1[0]

        if not (other_tore.contours2d[0].point_belongs(pt2_2d)):
            # Find the closest one
            points_contours2 = other_tore.contours2d[0].tessel_points

            poly2 = volmdlr.Polygon2D(points_contours2)
            d2, new_pt2_2d = poly2.PointBorderDistance(pt2_2d,
                                                       return_other_point=True)

            pt2 = self.points2d_to3d([new_pt2_2d], R2, r2, frame2)
            p2 = pt2[0]

        return p1, p2

    def minimum_distance_points_cyl(self, cyl):
        R2, r2, r = self.rcenter, self.rcircle, cyl.radius

        min_h, min_theta, max_h, max_theta = cyl.minimum_maximum(
            cyl.contours2d[0], r)

        n1 = cyl.normal
        u1 = cyl.cylindricalsurface3d.frame.u
        v1 = cyl.cylindricalsurface3d.frame.v
        frame1 = volmdlr.Frame3D(cyl.center, u1, v1, n1)
        # st1 = volmdlr.Point3D((r*math.cos(min_theta), r*math.sin(min_theta), min_h))
        # start1 = frame1.old_coordinates(st1)

        min_phi2, min_theta2, max_phi2, max_theta2 = self.minimum_maximum_tore(
            self.contours2d[0])

        n2 = self.normal
        u2 = self.toroidalsurface3d.frame.u
        v2 = self.toroidalsurface3d.frame.v
        frame2 = volmdlr.Frame3D(self.center, u2, v2, n2)
        # start2 = self.points2d_to3d([[min_theta2, min_phi2]], R2, r2, frame2)

        w = self.center - cyl.center

        n1n1, n1u1, n1v1, n1n2, n1u2, n1v2 = n1.dot(n1), n1.dot(u1), n1.dot(
            v1), n1.dot(n2), n1.dot(u2), n1.dot(v2)
        u1u1, u1v1, u1n2, u1u2, u1v2 = u1.dot(u1), u1.dot(v1), u1.dot(
            n2), u1.dot(u2), u1.dot(v2)
        v1v1, v1n2, v1u2, v1v2 = v1.dot(v1), v1.dot(n2), v1.dot(u2), v1.dot(v2)
        n2n2, n2u2, n2v2 = n2.dot(n2), n2.dot(u2), n2.dot(v2)
        u2u2, u2v2, v2v2 = u2.dot(u2), u2.dot(v2), v2.dot(v2)

        w2, wn1, wu1, wv1, wn2, wu2, wv2 = w.dot(w), w.dot(n1), w.dot(
            u1), w.dot(v1), w.dot(n2), w.dot(u2), w.dot(v2)

        # x = (theta, h, phi2, theta2)
        def distance_squared(x):
            return (u1u1 * ((math.cos(x[0]) * r) ** 2) + v1v1 * (
                        (math.sin(x[0]) * r) ** 2)
                    + n1n1 * (x[1] ** 2) + w2
                    + u2u2 * (((R2 + r2 * math.cos(x[2])) * math.cos(
                        x[3])) ** 2)
                    + v2v2 * (((R2 + r2 * math.cos(x[2])) * math.sin(
                        x[3])) ** 2)
                    + n2n2 * ((math.sin(x[2])) ** 2) * (r2 ** 2)
                    + 2 * u1v1 * math.cos(x[0]) * math.sin(x[0]) * (r ** 2)
                    + 2 * r * math.cos(x[0]) * x[1] * n1u1 - 2 * r * math.cos(
                        x[0]) * wu1
                    - 2 * r * math.cos(x[0]) * (
                                R2 + r2 * math.cos(x[2])) * math.cos(
                        x[3]) * u1u2
                    - 2 * r * math.cos(x[0]) * (
                                R2 + r2 * math.cos(x[2])) * math.sin(
                        x[3]) * u1v2
                    - 2 * r * math.cos(x[0]) * r2 * math.sin(x[2]) * u1n2
                    + 2 * r * math.sin(x[0]) * x[1] * n1v1 - 2 * r * math.sin(
                        x[0]) * wv1
                    - 2 * r * math.sin(x[0]) * (
                                R2 + r2 * math.cos(x[2])) * math.cos(
                        x[3]) * v1u2
                    - 2 * r * math.sin(x[0]) * (
                                R2 + r2 * math.cos(x[2])) * math.sin(
                        x[3]) * v1v2
                    - 2 * r * math.sin(x[0]) * r2 * math.sin(x[2]) * v1n2 - 2 *
                    x[1] * wn1
                    - 2 * x[1] * (R2 + r2 * math.cos(x[2])) * math.cos(
                        x[3]) * n1u2
                    - 2 * x[1] * (R2 + r2 * math.cos(x[2])) * math.sin(
                        x[3]) * n1v2
                    - 2 * x[1] * r2 * math.sin(x[2]) * n1n2
                    + 2 * (R2 + r2 * math.cos(x[2])) * math.cos(x[3]) * wu2
                    + 2 * (R2 + r2 * math.cos(x[2])) * math.sin(x[3]) * wv2
                    + 2 * r2 * math.sin(x[2]) * wn2
                    + 2 * u2v2 * math.cos(x[3]) * math.sin(x[3]) * (
                                (R2 + r2 * math.cos(x[2])) ** 2)
                    + 2 * math.cos(x[3]) * (
                                R2 + r2 * math.cos(x[2])) * r2 * math.sin(
                        x[2]) * n2u2
                    + 2 * math.sin(x[3]) * (
                                R2 + r2 * math.cos(x[2])) * r2 * math.sin(
                        x[2]) * n2v2)

        x01 = npy.array([(min_theta + max_theta) / 2, (min_h + max_h) / 2,
                         (min_phi2 + max_phi2) / 2,
                         (min_theta2 + max_theta2) / 2])
        x02 = npy.array([min_theta, min_h,
                         min_phi2, min_theta2])
        x03 = npy.array([max_theta, max_h,
                         max_phi2, max_theta2])

        minimax = [(min_theta, min_h, min_phi2, min_theta2),
                   (max_theta, max_h, max_phi2, max_theta2)]

        res1 = scp.optimize.least_squares(distance_squared, x01,
                                          bounds=minimax)
        res2 = scp.optimize.least_squares(distance_squared, x02,
                                          bounds=minimax)
        res3 = scp.optimize.least_squares(distance_squared, x03,
                                          bounds=minimax)

        pt1 = volmdlr.Point3D(
            (r * math.cos(res1.x[0]), r * math.sin(res1.x[0]), res1.x[1]))
        p1 = frame1.old_coordinates(pt1)
        pt2 = self.points2d_to3d([[res1.x[3], res1.x[2]]], R2, r2, frame2)
        p2 = pt2[0]
        d = p1.point_distance(p2)
        result = res1

        res = [res2, res3]
        for couple in res:
            pttest1 = volmdlr.Point3D((r * math.cos(couple.x[0]),
                               r * math.sin(couple.x[0]), couple.x[1]))
            ptest1 = frame1.old_coordinates(pttest1)
            ptest2 = self.points2d_to3d([[couple.x[3], couple.x[2]]], R2, r2,
                                        frame2)
            dtest = ptest1.point_distance(ptest2[0])
            if dtest < d:
                result = couple
                p1, p2 = ptest1, ptest2[0]

        pt1_2d, pt2_2d = volmdlr.Point2D((result.x[0], result.x[1])), volmdlr.Point2D(
            (result.x[3], result.x[2]))

        if not (self.contours2d[0].point_belongs(pt2_2d)):
            # Find the closest one
            points_contours2 = self.contours2d[0].tessel_points

            poly2 = volmdlr.Polygon2D(points_contours2)
            d2, new_pt2_2d = poly2.PointBorderDistance(pt2_2d,
                                                       return_other_point=True)

            pt2 = self.points2d_to3d([new_pt2_2d], R2, r2, frame2)
            p2 = pt2[0]

        if not (cyl.contours2d[0].point_belongs(pt1_2d)):
            # Find the closest one
            points_contours1 = cyl.contours2d[0].tessel_points

            poly1 = volmdlr.Polygon2D(points_contours1)
            d1, new_pt1_2d = poly1.PointBorderDistance(pt1_2d,
                                                       return_other_point=True)

            pt1 = volmdlr.Point3D((r * math.cos(new_pt1_2d.vector[0]),
                           r * math.sin(new_pt1_2d.vector[0]),
                           new_pt1_2d.vector[1]))
            p1 = frame1.old_coordinates(pt1)

        return p1, p2

    def minimum_distance_points_plane(self,
                                      planeface):  # Planeface with contour2D
        #### ADD THE FACT THAT PLANEFACE.CONTOURS : [0] = contours totale, le reste = trous

        poly2d = planeface.polygon2D
        pfpoints = poly2d.points
        xmin, ymin = min([pt[0] for pt in pfpoints]), min(
            [pt[1] for pt in pfpoints])
        xmax, ymax = max([pt[0] for pt in pfpoints]), max(
            [pt[1] for pt in pfpoints])
        origin, vx, vy = planeface.plane.origin, planeface.plane.vectors[0], \
                         planeface.plane.vectors[1]
        pf1_2d, pf2_2d = volmdlr.Point2D((xmin, ymin)), volmdlr.Point2D((xmin, ymax))
        pf3_2d, pf4_2d = volmdlr.Point2D((xmax, ymin)), volmdlr.Point2D((xmax, ymax))
        pf1, pf2 = pf1_2d.to_3d(origin, vx, vy), pf2_2d.to_3d(origin, vx, vy)
        pf3, _ = pf3_2d.to_3d(origin, vx, vy), pf4_2d.to_3d(origin, vx, vy)

        u, v = (pf3 - pf1), (pf2 - pf1)
        u.normalize()
        v.normalize()

        R1, r1 = self.rcenter, self.rcircle
        min_phi1, min_theta1, max_phi1, max_theta1 = self.minimum_maximum_tore(
            self.contours2d[0])

        n1 = self.normal
        u1 = self.toroidalsurface3d.frame.u
        v1 = self.toroidalsurface3d.frame.v
        frame1 = volmdlr.Frame3D(self.center, u1, v1, n1)
        # start1 = self.points2d_to3d([[min_theta1, min_phi1]], R1, r1, frame1)

        w = self.center - pf1

        n1n1, n1u1, n1v1, n1u, n1v = n1.dot(n1), n1.dot(u1), n1.dot(
            v1), n1.dot(u), n1.dot(v)
        u1u1, u1v1, u1u, u1v = u1.dot(u1), u1.dot(v1), u1.dot(u), u1.dot(v)
        v1v1, v1u, v1v = v1.dot(v1), v1.dot(u), v1.dot(v)
        uu, uv, vv = u.dot(u), u.dot(v), v.dot(v)

        w2, wn1, wu1, wv1, wu, wv = w.dot(w), w.dot(n1), w.dot(u1), w.dot(
            v1), w.dot(u), w.dot(v)

        # x = (x, y, phi1, theta1)
        def distance_squared(x):
            return (uu * (x[0] ** 2) + vv * (x[1] ** 2) + w2
                    + u1u1 * (((R1 + r1 * math.cos(x[2])) * math.cos(
                        x[3])) ** 2)
                    + v1v1 * (((R1 + r1 * math.cos(x[2])) * math.sin(
                        x[3])) ** 2)
                    + n1n1 * ((math.sin(x[2])) ** 2) * (r1 ** 2)
                    + 2 * x[0] * x[1] * uv - 2 * x[0] * wu
                    - 2 * x[0] * (R1 + r1 * math.cos(x[2])) * math.cos(
                        x[3]) * u1u
                    - 2 * x[0] * (R1 + r1 * math.cos(x[2])) * math.sin(
                        x[3]) * v1u
                    - 2 * x[0] * math.sin(x[2]) * r1 * n1u - 2 * x[1] * wv
                    - 2 * x[1] * (R1 + r1 * math.cos(x[2])) * math.cos(
                        x[3]) * u1v
                    - 2 * x[1] * (R1 + r1 * math.cos(x[2])) * math.sin(
                        x[3]) * v1v
                    - 2 * x[1] * math.sin(x[2]) * r1 * n1v
                    + 2 * (R1 + r1 * math.cos(x[2])) * math.cos(x[3]) * wu1
                    + 2 * (R1 + r1 * math.cos(x[2])) * math.sin(x[3]) * wv1
                    + 2 * math.sin(x[2]) * r1 * wn1
                    + 2 * u1v1 * math.cos(x[3]) * math.sin(x[3]) * (
                                (R1 + r1 * math.cos(x[2])) ** 2)
                    + 2 * (R1 + r1 * math.cos(x[2])) * math.cos(
                        x[3]) * r1 * math.sin(x[2]) * n1u1
                    + 2 * (R1 + r1 * math.cos(x[2])) * math.sin(
                        x[3]) * r1 * math.sin(x[2]) * n1v1)

        x01 = npy.array([(xmax - xmin) / 2, (ymax - ymin) / 2,
                         (min_phi1 + max_phi1) / 2,
                         (min_theta1 + max_theta1) / 2])

        minimax = [(0, 0, min_phi1, min_theta1),
                   (xmax - xmin, ymax - ymin, max_phi1, max_theta1)]

        res1 = scp.optimize.least_squares(distance_squared, x01,
                                          bounds=minimax)

        # frame1 = volmdlr.Frame3D(self.center, u1, v1, n1)
        pt1 = self.points2d_to3d([[res1.x[3], res1.x[2]]], R1, r1, frame1)
        p1 = pt1[0]
        p2 = pf1 + res1.x[2] * u + res1.x[3] * v

        pt1_2d = volmdlr.Point2D((res1.x[3], res1.x[2]))
        pt2_2d = p2.to_2d(pf1, u, v)

        if not (self.contours2d[0].point_belongs(pt1_2d)):
            # Find the closest one
            points_contours1 = self.contours2d[0].tessel_points

            poly1 = volmdlr.Polygon2D(points_contours1)
            d1, new_pt1_2d = poly1.PointBorderDistance(pt1_2d,
                                                       return_other_point=True)

            pt1 = self.points2d_to3d([new_pt1_2d], R1, r1, frame1)
            p1 = pt1[0]

        if not (planeface.contours[0].point_belongs(pt2_2d)):
            # Find the closest one
            d2, new_pt2_2d = planeface.polygon2D.PointBorderDistance(pt2_2d,
                                                                     return_other_point=True)

            p2 = new_pt2_2d.to_3d(pf1, u, v)

        return p1, p2

    def minimum_distance(self, other_face, return_points=False):
        if other_face.__class__ is ToroidalFace3D:
            p1, p2 = self.minimum_distance_points_tore(other_face)
            if return_points:
                return p1.point_distance(p2), p1, p2
            else:
                return p1.point_distance(p2)

        if other_face.__class__ is CylindricalFace3D:
            p1, p2 = self.minimum_distance_points_cyl(other_face)
            if return_points:
                return p1.point_distance(p2), p1, p2
            else:
                return p1.point_distance(p2)

        if other_face.__class__ is PlaneFace3D:
            p1, p2 = self.minimum_distance_points_plane(other_face)
            if return_points:
                return p1.point_distance(p2), p1, p2
            else:
                return p1.point_distance(p2)
        else:
            return NotImplementedError


class ConicalFace3D(Face3D):
    """
    :param contours2d: The Cone's contour2D
    :type contours2d: volmdlr.Contour2D
    :param conicalsurface3d: Information about the Cone
    :type conicalsurface3d: ConicalSurface3D
    :param points: Contour2d's parameter Cone
    :type points: List of float

    """
    min_x_density = 5
    min_y_density = 1

    def __init__(self, conicalsurface3d: ConicalSurface3D,
                 outer_contour2d: volmdlr.wires.Contour2D,
                 inner_contours2d: List[volmdlr.wires.Contour2D],
                 name: str = ''):

        Face3D.__init__(self,
                        surface=conicalsurface3d,
                        outer_contour2d=outer_contour2d,
                        inner_contours2d=inner_contours2d,
                        name=name)

    def create_triangle(self, all_contours_points, part):
        Triangles, ts = [], []
        pts, h_list = [], []
        for listpt in all_contours_points:
            for pt in listpt:
                pts.append(pt)
                h_list.append(pt[1])
        if part == 'bot':
            h_concerned = min(h_list)
        else:
            h_concerned = max(h_list)
        peak_list, other = [], []
        for pt in pts:
            if pt[1] == h_concerned:
                peak_list.append(pt)
            else:
                other.append(pt)
        points = [peak_list[0]] + other

        for i in range(1, len(points)):
            if i == len(points) - 1:
                vertices = [points[i].vector, points[0].vector,
                            points[1].vector]
                segments = [[0, 1], [1, 2], [2, 0]]
                listindice = [i, 0, 1]
            else:
                vertices = [points[i].vector, points[0].vector,
                            points[i + 1].vector]
                segments = [[0, 1], [1, 2], [2, 0]]
                listindice = [i, 0, i + 1]
            tri = {'vertices': vertices, 'segments': segments}
            t = triangle.triangulate(tri, 'p')
            if 'triangles' in t:
                triangles = t['triangles'].tolist()
                triangles[0] = listindice
                Triangles.append(triangles)
            else:
                Triangles.append(None)
            ts.append(t)

        return points, Triangles


class SphericalFace3D(Face3D):
    """
    :param contours2d: The Sphere's contour2D
    :type contours2d: volmdlr.Contour2D
    :param sphericalsurface3d: Information about the Sphere
    :type sphericalsurface3d: SphericalSurface3D
    :param points: Angle's Sphere
    :type points: List of float

    """
    min_x_density = 5
    min_y_density = 5

    def __init__(self, spherical_surface3d:SphericalSurface3D,
                 outer_contour2d: volmdlr.wires.Contour2D,
                 inner_contours2d: List[volmdlr.wires.Contour2D],
                 name: str = ''):
        Face3D.__init__(self,
                        surface=spherical_surface3d,
                        outer_contour2d=outer_contour2d,
                        inner_contours2d=inner_contours2d,
                        name=name)

    @classmethod
    def from_contour3d(cls, contours3d, sphericalsurface3d, name=''):
        """
        :param contours3d: The Sphere's contour3D
        :type contours3d: Contour3D
        :param sphericalsurface3d: Information about the Sphere
        :type sphericalsurface3d: SphericalSurface3D

        """
        frame = sphericalsurface3d.frame
        center = frame.origin
        normal = frame.w
        # r = sphericalsurface3d.radius

        if contours3d[0].__class__ is volmdlr.Point3D:  # If it is a complete sphere
            angle = volmdlr.TWO_PI
            pt1, pt2, pt3, pt4 = volmdlr.Point2D((0, 0)), volmdlr.Point2D((0, angle)), volmdlr.Point2D(
                (angle, angle)), volmdlr.Point2D((angle, 0))
            seg1, seg2, seg3, seg4 = volmdlr.LineSegment2D(pt1, pt2), volmdlr.LineSegment2D(
                pt2, pt3), volmdlr.LineSegment2D(pt3, pt4), volmdlr.LineSegment2D(pt4, pt1)
            primitives = [seg1, seg2, seg3, seg4]
            contours2d = [volmdlr.Contour2D(primitives)]
            points = [angle, angle]

        elif contours3d[0].edges[0].__class__ is Arc3D and contours3d[0].edges[
            1].__class__ is Arc3D:  # Portion of Sphere
            ## we supposed a contours with 4 edges maximum here
            arc_base, arc_link = [], []
            range_list = []
            for edge in contours3d[0].edges:
                if edge.normal == normal:
                    arc_base.append(edge)
                    range_list.append(1)
                else:
                    arc_link.append(edge)
                    range_list.append(2)
            if len(arc_base) == 0:
                raise NotImplementedError

            theta = arc_base[0].angle
            phi = arc_link[0].angle
            if range_list[-1] == range_list[-2]:
                offset_phi = -math.pi / 2
            else:
                pos = len(arc_base) - 1
                c1 = arc_base[pos].center
                vec1, vec2 = c1 - center, arc_base[pos].start - center
                offset_phi = -math.pi / 2 + vectors3d_angle(vec1, vec2)
            offset_theta = 0

            # Creation of the window
            pt1, pt2, pt3, pt4 = volmdlr.Point2D((offset_theta, offset_phi)), volmdlr.Point2D(
                (offset_theta, offset_phi + phi)), volmdlr.Point2D(
                (offset_theta + theta, offset_phi + phi)), volmdlr.Point2D(
                (offset_theta + theta, offset_phi))
            seg1, seg2, seg3, seg4 = volmdlr.LineSegment2D(pt1, pt2), volmdlr.LineSegment2D(
                pt2, pt3), volmdlr.LineSegment2D(pt3, pt4), volmdlr.LineSegment2D(pt4, pt1)
            primitives = [seg1, seg2, seg3, seg4]
            contours2d = [volmdlr.Contour2D(primitives)]
            points = [theta, phi]

            # fig, ax = plt.subplots()
            # [prim.MPLPlot(ax=ax) for prim in primitives]

        else:
            contours2d = SphericalFace3D.contours3d_to2d(contours3d,
                                                         sphericalsurface3d)
            theta = max(pt[0] for pt in contours2d[0].tessel_points) - min(
                pt[0] for pt in contours2d[0].tessel_points)
            phi = max(pt[1] for pt in contours2d[0].tessel_points) - min(
                pt[1] for pt in contours2d[0].tessel_points)
            points = [theta, phi]
            # print('contours3d edges', contours3d[0].edges)
            # raise NotImplementedError

        return cls(contours2d, sphericalsurface3d, points, name=name)

class RuledFace3D(Face3D):
    """

    """
    min_x_density = 50
    min_y_density = 1

    def __init__(self,
                 ruledsurface3d: RuledSurface3D,
                 surface2d: Surface2D,
                 name: str = ''):

        Face3D.__init__(self, surface3d=ruledsurface3d,
                        surface2d=surface2d,
                        name=name)


class BSplineFace3D(Face3D):
    def __init__(self, bspline_surface:BSplineSurface3D,
                 outer_contour2d: volmdlr.wires.Contour2D,
                 inner_contours2d: List[volmdlr.wires.Contour2D],
                 name: str = ''):
        Face3D.__init__(self,
                        surface=bspline_surface,
                        outer_contour2d=outer_contour2d,
                        inner_contours2d=inner_contours2d,
                        name=name)


SURFACE_TO_FACE = {Plane3D: PlaneFace3D,
                   CylindricalSurface3D: CylindricalFace3D,
                   ToroidalSurface3D: ToroidalFace3D,
                   ConicalSurface3D: ConicalFace3D}